from dateutil import parser as dateparser

DATETIME_INTERVAL_CLOSED_SYMBOL = "/"
DATETIME_INTERVAL_OPEN_START_SYMBOL  = "../"
DATETIME_INTERVAL_OPEN_END_SYMBOL = "/.."


def datetime_interval_parser(datetime_interval):

    parsed_datetime = {}

    if datetime_interval.startswith(DATETIME_INTERVAL_OPEN_START_SYMBOL):
        datetime_interval = datetime_interval.replace(DATETIME_INTERVAL_OPEN_START_SYMBOL,'')
        parsed_datetime["before"] = dateparser.parse(datetime_interval)
    
    elif datetime_interval.endswith(DATETIME_INTERVAL_OPEN_END_SYMBOL):
        datetime_interval = datetime_interval.replace(DATETIME_INTERVAL_OPEN_END_SYMBOL,'')
        parsed_datetime["after"] = dateparser.parse(datetime_interval)
    
    elif DATETIME_INTERVAL_CLOSED_SYMBOL in datetime_interval:
        datetime_interval = datetime_interval.split(DATETIME_INTERVAL_CLOSED_SYMBOL)
        parsed_datetime["after"] = dateparser.parse(datetime_interval[0])
        parsed_datetime["before"] = dateparser.parse(datetime_interval[-1])
    else:
        parsed_datetime["match"] = dateparser.parse(datetime_interval)

    return parsed_datetime