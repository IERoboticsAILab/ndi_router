import time
from cyndilib.finder import Finder

def list_all_ndi_sources(timeout=3.0):
    finder = Finder()
    finder.open()

    end_time = time.time() + timeout
    while time.time() < end_time:
        changed = finder.wait_for_sources(timeout=end_time - time.time())
        if changed:
            finder.update_sources()
        time.sleep(0.1)

    results = []
    for src in finder.iter_sources():
        # .name is like "host (stream)", .host_name is separate
        results.append({
            "name": src.name,
            "host": src.host_name,
            "stream": src.stream_name
        })

    finder.close()
    return results

if __name__ == "__main__":
    sources = list_all_ndi_sources()
    print(sources)
