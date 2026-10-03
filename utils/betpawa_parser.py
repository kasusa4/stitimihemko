import struct

def read_varint(data, pos):
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
    return None, pos

def parse_fields(data):
    """Parse top-level protobuf fields into a dict {field_number: [values]}."""
    fields = {}
    pos = 0
    while pos < len(data):
        tag, pos = read_varint(data, pos)
        if tag is None:
            break
        field_num = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 2:  # length-delimited
            length, pos = read_varint(data, pos)
            value = data[pos:pos+length]
            pos += length
            fields.setdefault(field_num, []).append(value)
        elif wire_type == 0:  # varint
            val, pos = read_varint(data, pos)
            fields.setdefault(field_num, []).append(val)
        elif wire_type == 5:  # 32-bit
            val = data[pos:pos+4]
            pos += 4
            fields.setdefault(field_num, []).append(val)
        elif wire_type == 1:  # 64-bit
            val = data[pos:pos+8]
            pos += 8
            fields.setdefault(field_num, []).append(val)
        else:
            break
    return fields

def parse_team_name(team_bytes):
    f = parse_fields(team_bytes)
    if 2 in f:
        return f[2][0].decode(errors='ignore')
    return None

def parse_scores(scores_bytes):
    """Extract full-time scores from the scores message."""
    f = parse_fields(scores_bytes)
    result = {'ft_home': None, 'ft_away': None}
    if 2 in f:
        for side_bytes in f[2]:
            side = parse_fields(side_bytes)
            side_label = None
            if 1 in side:
                side_info = parse_fields(side[1][0])
                if 2 in side_info:
                    side_label = side_info[2][0].decode(errors='ignore')
            if 2 in side and side_label:
                for score_bytes in side[2]:
                    score = parse_fields(score_bytes)
                    market = None
                    if 1 in score:
                        market_info = parse_fields(score[1][0])
                        if 3 in market_info:
                            market = market_info[3][0].decode(errors='ignore')
                    if market == 'FULL_TIME_EXCLUDING_OVERTIME' and 2 in score:
                        val = score[2][0].decode(errors='ignore')
                        try:
                            val_int = int(val)
                        except ValueError:
                            continue
                        if side_label == 'HOME':
                            result['ft_home'] = val_int
                        elif side_label == 'AWAY':
                            result['ft_away'] = val_int
    return result

def parse_event(event_bytes):
    """Parse one event (match) from its Protobuf bytes."""
    fields = parse_fields(event_bytes)
    result = {}
    # Event ID (field 1)
    if 1 in fields:
        result['event_id'] = fields[1][0].decode(errors='ignore')
    # Teams (field 5)
    if 5 in fields and len(fields[5]) >= 2:
        result['home_team'] = parse_team_name(fields[5][0])
        result['away_team'] = parse_team_name(fields[5][1])
    # Scores (field 3)
    if 3 in fields:
        scores = parse_scores(fields[3][0])
        result.update(scores)
    # League (field 12)
    if 12 in fields:
        league_fields = parse_fields(fields[12][0])
        if 2 in league_fields:
            result['league'] = league_fields[2][0].decode(errors='ignore')
    return result

def parse_events_response(response_bytes):
    """Parse the events response and return a list of event dicts."""
    top = parse_fields(response_bytes)
    events = []
    if 2 in top:
        for event_bytes in top[2]:
            events.append(parse_event(event_bytes))
    return events