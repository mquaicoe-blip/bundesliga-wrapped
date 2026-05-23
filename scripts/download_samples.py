import sys, os, pathlib
sys.path.insert(0, '.')
os.environ['HACKATHON_BUCKET'] = 'hackathon-data-119997536330'
from backend.data.s3_loader import download_file, list_challenge_files

pathlib.Path('data/raw').mkdir(parents=True, exist_ok=True)

PREFIX = 'Challenge 1 \u2013 Build Bundesliga Wrapped/'

targets = {
    'main_json':    PREFIX + 'data/bundesliga_wrapped_challenge_dataset.json',
    'clubs_xml':    PREFIX + 'data/feeds-exports-24-25/01.04.Clubs.xml',
    'schedule_xml': PREFIX + 'data/feeds-exports-24-25/01.06.Spielplan.xml',
    'bayern_xml':   PREFIX + 'data/1K8_Bayern.xml',
    'data_ref':     PREFIX + 'documentation/DATA_REFERENCE.md',
}

for name, key in targets.items():
    filename = key.split('/')[-1]
    dest = f'data/raw/{filename}'
    download_file(key, dest)
    print(f'OK: {dest}')

# Also grab first 2 player XMLs
all_keys = list_challenge_files('data/feeds-exports-24-25/players/')
for key in all_keys[:2]:
    filename = key.split('/')[-1]
    dest = f'data/raw/player_{filename}'
    download_file(key, dest)
    print(f'OK: {dest}')

# First 2 match XMLs
all_keys = list_challenge_files('data/feeds-exports-24-25/matches/')
for key in all_keys[:2]:
    filename = key.split('/')[-1]
    dest = f'data/raw/match_{filename}'
    download_file(key, dest)
    print(f'OK: {dest}')
