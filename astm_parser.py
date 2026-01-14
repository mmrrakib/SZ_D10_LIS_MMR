def parse_astm(astm_string):
    """
    Parses a simplified ASTM message string and extracts relevant data.
    This is a basic parser for demonstration and not a full ASTM implementation.
    """
    data = {}
    segments = astm_string.strip().split('\r')

    for segment in segments:
        fields = segment.split('|')
        segment_type = fields[0]

        if segment_type == 'O': # Order record
            # O|1|{sample_id}||^^^{test_name}|R
            if len(fields) > 2:
                data['sample_id'] = fields[2]
            if len(fields) > 4:
                # Component field: ^^^{test_name}
                components = fields[4].split('^')
                if len(components) > 3:
                    data['test_name'] = components[3]
        
        elif segment_type == 'R': # Result record
            # R|1|^^^{test_name}|{value}|{units}|{ref_range}|N||{status}|||{timestamp}
            if len(fields) > 3:
                data['value'] = fields[3]
            if len(fields) > 4: # Extract unit from 5th field (index 4)
                data['unit'] = fields[4]
            if len(fields) > 5:
                data['ref_range'] = fields[5]
            if len(fields) > 8:
                data['status'] = fields[8]
            if len(fields) > 11:
                data['datetime'] = fields[11]

    return data
