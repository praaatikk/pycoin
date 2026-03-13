import os
import json

# ----------------------------------------------------
# Base database class for reading/writing JSON files
# ----------------------------------------------------
class BaseDB:
    def __init__(self):
        if not hasattr(self, "filename"):
            raise AttributeError("Derived class must set 'filename'")
        self.basepath = "data"
        os.makedirs(self.basepath, exist_ok=True)
        self.filepath = os.path.join(self.basepath, self.filename + ".json")

    def read(self):
        if not os.path.exists(self.filepath):
            print(f"File {self.filepath} not available")
            return []

        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
                if not isinstance(data, list):
                    print(f"Warning: {self.filepath} content is invalid, resetting to empty list")
                    return []
                return data
        except json.JSONDecodeError:
            print(f"Error: {self.filepath} contains invalid JSON, resetting to empty list")
            return []
        except Exception as e:
            print(f"Unexpected error reading {self.filepath}: {e}")
            return []

    def write(self, data):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)
        except Exception as e:
            print(f"Error writing to {self.filepath}: {e}")


# ----------------------------------------------------
# Blockchain-specific database
# ----------------------------------------------------
class BlockchainDB(BaseDB):
    def __init__(self, filename="blockchain"):
        self.filename = filename
        super().__init__()

    def write(self, blocks):
        existing_blocks = self.read()
        existing_blocks.extend(blocks)
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(existing_blocks, f, indent=4)

    def lastBlock(self):
        blocks = self.read()
        if not blocks:
            return None
        return blocks[-1]


# ----------------------------------------------------
# Account database
# ----------------------------------------------------
class AccountDB(BaseDB):
    def __init__(self, filename="account"):
        self.filename = filename
        super().__init__()

    def add_account(self, account):
        """
        Appends a new account to account.json.
        account should be a dict: {privateKey, PublicAddress}
        Returns False if address already exists.
        """
        accounts = self.read()

        # check for duplicate address
        for acc in accounts:
            if acc["PublicAddress"] == account["PublicAddress"]:
                print(f"Account {account['PublicAddress']} already exists")
                return False

        accounts.append(account)
        self.write(accounts)
        print(f"New account created: {account['PublicAddress']}")
        return True