from bisect import bisect_right


def index_windows(sites):
    windows = sorted((site['at_mm'] - site['window_mm'], site['at_mm'] + site['window_mm'], site['site_id'])
                     for site in sites)
    return [window[0] for window in windows], windows


def candidates(index, position):
    starts, windows = index
    return [site_id for _, end, site_id in windows[:bisect_right(starts, position)] if position <= end]
