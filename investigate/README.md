# Ivestigation of similarities search with Simhashes

## Brief description
The main idea is to store simhash of each text (for section of the bill, for the subsections and the whole bill) in DB and perform search with DB functionality - BIT_COUNT() function

BIT COUNT performs a bit operation with result of XOR between to hashes and it is quite fast.
A xor B aka `A ^ B` is operation for counting Hamming distance between `A` and `B`.

Hash of the text is a locality sensitive hashing functions. 
In contrary to crypto hashes (SHA, MD5), where even small change of the input leads to significant changes of the output result of the hash function, 
locality sensitive hashing function operates in opposite way and mostly insensitive to minor changes of the input string.
Under the hood it may work with ngrams of the input text or with text shingles. 
The process of hashing quite close to counting bit average of hashes among all the input ngrams/shingles.
This way, mostly similar texts will have very close or even the same hashes. 
If we have 128 bit length hash, we can consider two input text very similar if their hashes have the Hamming distance less than 12/128 (9.3% difference, 90.7% similar). 

And this measure of the similarity is adjustable - the larger Hamming distance, the wider range of similar texts we can find.
For distance 35/128 we will have all texts that have 80.5% of similarity (19.5% difference) and so on.


## 4 steps to success
### 1. Create environment and install dependencies

Run `pip install -r investigate/requirements.txt`

### 2. Establish DB connection
Create config file from the template:
`cp investigate/config.yaml.template investigate/config.yaml`

Then type into `config.yaml` your credentials to connect to DB: 
```
user: <your_db_user_name>
password: <your_password>
```

Create DB table with command:
```
cd investigate
python investigate/main_test.py -create_db
```

### 3. Fix folder names/ paths

Since all xml bills are not included to this repo it is supposed that you already have them so just specify in the script from which folder you want to load and parse them.

Provide correct full path to all bills in `config.yaml`

It should look like:
`CONGRESS_ROOT_FOLDER: '/Users/dmytroustynov/programm/congress.nosync/data'`


### 4. Run the script
You may load DB with bills , with sections, or both them at once.

To load bills run the command:
`python main_tests.py -bills`

To load sections run the command:
`python main_tests.py -sections`. This also creates corresponding _bill_path_ entities to link sections, files, and their path on your disk)

To load them all:
`python main_tests.py -all`. This will create all data in a single run: bills, sections and their paths

It will take some time to proceed all files and load > 100k entities to DB, so be patient and let the script run.

**WARNING:**
There is no protection of uniqueness texts/hashes or any other check
if the text/paragraph was already loaded to DB table or not.
So run previous commands only once, or truncate table first, otherwise you create a lot of duplicates,
 and further search of similar will produce a bunch of noise results.


## Useful utils

All utility functions are in `investigate\utils.py`.
Text cleaning, establishing connection to DB, reading files from folder, building simhashes etc.

Also added an implementation for 128bit hash of fnv-1a hashing function, which is quite useful for Simhash due to its simplicity and swift operation.

## Test search

Once DB is loaded with texts, you can test how the similarity search works running `investigate\test_search.py` with different values
or adding similar texts to find by hand. 
Works among bills, but may also perform search among sections.

