# Ivestigation of similarities search with Simhashes

## Brief description
The main idea is to store simhash of each section of the bill in DB and perform search with DB functionality (BIT_COUNT)

BIT COUNT performs a bit operation with result of XOR between to integers (hashes) and it is quite fast.
A xor B aka `A ^ B` is operation for counting Hamming distance between `A` and `B`.


## 3 steps to success
### 1. Create environment and install dependencies

Run `pip install -r investigate/requirements.txt`

Create DB table with sql script from `investigate/create_table.sql`

Create config file from template:
`cp investigate/config.yaml.template investigate/config.yaml`

Then place into `config.yaml` your credentials to connect to DB.

### 2. Fix folder names/ paths

Since all xml bills are not included to this repo it is supposed that you already have them so just specify in the script from which folder you want to load and parse them.

### 3. Run the script
You can change file names to check how the similarity search works with other files

