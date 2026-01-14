from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, or_, and_
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, joinedload
from sqlalchemy.sql import distinct
import datetime

DATABASE_URL = "sqlite:///machinedb.db"

Base = declarative_base()

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, unique=True, index=True)
    name = Column(String)
    age = Column(String)
    gender = Column(String)
    phone_number = Column(String)

    results = relationship("ResultDetails", back_populates="patient")

class ResultDetails(Base):
    __tablename__ = "result_details"

    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(String, index=True)
    test_name = Column(String)
    test_result = Column(String)
    unit = Column(String)
    reference_range = Column(String)
    date_time = Column(DateTime, default=datetime.datetime.now)

    patient_id = Column(Integer, ForeignKey("patients.id"))
    patient = relationship("Patient", back_populates="results")

    # New fields for verification
    verified_by_doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    verified_by_doctor = relationship("Doctor", backref="verified_results", foreign_keys=[verified_by_doctor_id])

    # New fields for finalization
    finalized_by_doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    finalized_by_doctor = relationship("Doctor", backref="finalized_results", foreign_keys=[finalized_by_doctor_id])
    status = Column(String, default="Pending") # Status: Pending, Verified, Finalized

class MachineConfig(Base):
    __tablename__ = "machine_config"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, unique=True, index=True)
    ip = Column(String)
    port = Column(String)

class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(String, unique=True, index=True) # DOC0000001
    name = Column(String)
    designation = Column(String)
    age = Column(Integer)
    gender = Column(String) # 'Male', 'Female', 'Others'
    phone_number = Column(String)
    type = Column(String) # 'Verification', 'Finalization', 'Both'

# Create the database engine
engine = create_engine(DATABASE_URL)

# Create tables if they don't exist
Base.metadata.create_all(engine)

# Create a session to interact with the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def insert_result_details(db_session, sample_id, test_name, test_result, unit, reference_range, date_time=None):
    if date_time is None:
        date_time = datetime.datetime.now()
    db_result = ResultDetails(
        sample_id=sample_id,
        test_name=test_name,
        test_result=test_result,
        unit=unit,
        reference_range=reference_range,
        date_time=date_time
    )
    db_session.add(db_result)
    db_session.commit()
    db_session.refresh(db_result)
    return db_result

def get_machine_config(db_session):
    return db_session.query(MachineConfig).first()

def update_single_machine_config(db_session, machine_id, ip, port):
    config = db_session.query(MachineConfig).first()
    if config:
        config.machine_id = machine_id
        config.ip = ip
        config.port = port
    else:
        config = MachineConfig(machine_id=machine_id, ip=ip, port=port)
        db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config

def get_next_patient_id(db_session):
    last_patient = db_session.query(Patient).order_by(Patient.id.desc()).first()
    if last_patient and last_patient.patient_id:
        last_id = int(last_patient.patient_id[1:])
        new_id = last_id + 1
        return f"P{new_id:07d}"
    return "P0000001"

def create_patient_for_result(db_session, result_id, name, age, gender, phone_number):
    result = db_session.query(ResultDetails).filter(ResultDetails.id == result_id).first()
    if not result:
        return None

    if result.patient:
        patient = result.patient
        patient.name = name
        patient.age = age
        patient.gender = gender
        patient.phone_number = phone_number
    else:
        patient = Patient(
            patient_id=get_next_patient_id(db_session),
            name=name,
            age=age,
            gender=gender,
            phone_number=phone_number
        )
        result.patient = patient
        db_session.add(patient)
    
    db_session.commit()
    db_session.refresh(patient)
    return patient

def get_patient_by_result_id(db_session, result_id):
    result = db_session.query(ResultDetails).filter(ResultDetails.id == result_id).first()
    return result.patient if result else None

def get_result_by_id(db_session, result_id):
    return db_session.query(ResultDetails).filter(ResultDetails.id == result_id).first()

def search_patients(db_session, name=None, phone_number=None, sample_id=None, patient_id=None):
    query = db_session.query(Patient).distinct(Patient.id)
    
    if sample_id:
        query = query.join(ResultDetails).filter(ResultDetails.sample_id.like(f"%{sample_id}%"))

    filters = []
    if name:
        filters.append(Patient.name.like(f"%{name}%"))
    if phone_number:
        filters.append(Patient.phone_number.like(f"%{phone_number}%"))
    if patient_id:
        filters.append(Patient.patient_id.like(f"%{patient_id}%"))
    
    if filters:
        query = query.filter(and_(*filters))
        
    return query.all()

def search_results(db_session, sample_id=None, patient_id=None, patient_name=None, test_name=None, from_date=None, to_date=None, without_patient_info=False):
    query = db_session.query(ResultDetails)
    
    filters = []
    if sample_id:
        filters.append(ResultDetails.sample_id.like(f"%{sample_id}%"))
    
    if patient_id or patient_name:
        query = query.join(Patient)
        if patient_id:
            filters.append(Patient.patient_id.like(f"%{patient_id}%"))
        if patient_name:
            filters.append(Patient.name.like(f"%{patient_name}%"))
    elif without_patient_info:
        query = query.outerjoin(Patient).filter(ResultDetails.patient_id == None)

    if test_name:
        filters.append(ResultDetails.test_name.like(f"%{test_name}%"))
    
    if from_date:
        query = query.filter(ResultDetails.date_time >= from_date)
    
    if to_date:
        query = query.filter(ResultDetails.date_time <= to_date + datetime.timedelta(days=1))

    if filters:
        query = query.filter(and_(*filters))

    return query.options(joinedload(ResultDetails.patient)).all()

def get_patient_with_all_results(db_session, patient_id):
    return db_session.query(Patient).options(joinedload(Patient.results)).filter(Patient.id == patient_id).first()

def get_patient_by_patient_id(db_session, patient_id):
    return db_session.query(Patient).options(joinedload(Patient.results)).filter(Patient.patient_id == patient_id).first()

def get_next_doctor_id(db_session):
    last_doctor = db_session.query(Doctor).order_by(Doctor.id.desc()).first()
    if last_doctor and last_doctor.doctor_id:
        last_id_num = int(last_doctor.doctor_id[3:]) # Extract number part
        new_id_num = last_id_num + 1
        return f"DOC{new_id_num:07d}"
    return "DOC0000001"

def add_doctor(db_session, name, designation, age, gender, phone_number, doctor_type):
    doctor_id = get_next_doctor_id(db_session)
    new_doctor = Doctor(
        doctor_id=doctor_id,
        name=name,
        designation=designation,
        age=age,
        gender=gender,
        phone_number=phone_number,
        type=doctor_type
    )
    db_session.add(new_doctor)
    db_session.commit()
    db_session.refresh(new_doctor)
    return new_doctor

def get_all_doctors(db_session):
    return db_session.query(Doctor).all()

def search_doctors(db_session, name=None, doctor_id=None, phone_number=None):
    query = db_session.query(Doctor)
    filters = []
    if name:
        filters.append(Doctor.name.like(f"%{name}%"))
    if doctor_id:
        filters.append(Doctor.doctor_id.like(f"%{doctor_id}%"))
    if phone_number:
        filters.append(Doctor.phone_number.like(f"%{phone_number}%"))
    
    if filters:
        query = query.filter(and_(*filters))
    
    return query.all()

def get_doctors_by_type(db_session, required_type=None):
    query = db_session.query(Doctor)
    if required_type:
        # Check if type is 'Both' or the specific type requested
        query = query.filter(or_(Doctor.type == required_type, Doctor.type == "Both"))
    return query.all()

def update_result_verification(db_session, result_id, doctor_id):
    result = db_session.query(ResultDetails).filter(ResultDetails.id == result_id).first()
    if result:
        result.verified_by_doctor_id = doctor_id
        result.status = "Verified" # Set status to Verified
        db_session.commit()
        db_session.refresh(result)
        return result
    return None

def update_result_finalization(db_session, result_id, doctor_id):
    result = db_session.query(ResultDetails).filter(ResultDetails.id == result_id).first()
    if result:
        # If the result is pending, the finalizing doctor also verifies it.
        if result.status == "Pending":
            result.verified_by_doctor_id = doctor_id
        
        result.finalized_by_doctor_id = doctor_id
        result.status = "Finalized" # Set status to Finalized
        db_session.commit()
        db_session.refresh(result)
        return result
    return None

def search_results(db_session, sample_id=None, patient_id=None, patient_name=None, test_name=None, from_date=None, to_date=None, without_patient_info=False, status=None):
    query = db_session.query(ResultDetails)
    
    filters = []
    if sample_id:
        filters.append(ResultDetails.sample_id.like(f"%{sample_id}%"))
    
    if patient_id or patient_name:
        query = query.join(Patient)
        if patient_id:
            filters.append(Patient.patient_id.like(f"%{patient_id}%"))
        if patient_name:
            filters.append(Patient.name.like(f"%{patient_name}%"))
    elif without_patient_info:
        query = query.outerjoin(Patient).filter(ResultDetails.patient_id == None)

    if test_name:
        filters.append(ResultDetails.test_name.like(f"%{test_name}%"))
    
    if from_date:
        query = query.filter(ResultDetails.date_time >= from_date)
    
    if to_date:
        query = query.filter(ResultDetails.date_time <= to_date + datetime.timedelta(days=1))

    if status and status != "All": # Added status filter
        filters.append(ResultDetails.status == status)

    if filters:
        query = query.filter(and_(*filters))

    return query.options(joinedload(ResultDetails.patient), joinedload(ResultDetails.verified_by_doctor), joinedload(ResultDetails.finalized_by_doctor)).all() # Eagerly load finalized_by_doctor

def get_result_by_id_with_patient_and_doctor(db_session, result_id):
    return db_session.query(ResultDetails)\
        .options(joinedload(ResultDetails.patient))\
        .options(joinedload(ResultDetails.verified_by_doctor))\
        .options(joinedload(ResultDetails.finalized_by_doctor))\
        .filter(ResultDetails.id == result_id).first()