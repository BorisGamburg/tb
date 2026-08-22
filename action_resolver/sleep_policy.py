def get_sleep_interval(tf) -> int:
    tf_int = int(tf)
    if tf_int == 1:
        interval = 5
    elif tf_int in [3,5]:
        interval = 20
    elif tf_int in [10, 15, 30]:
        interval = 60
    else:
        interval = 120
        
    return interval
