from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey, N
from Blockchain.Backend.core.database.database import AccountDB
from random import randint


class CreateWallet:
    """
    Generates a new Bitcoin-style wallet with a private key and public address.
    Saves it to account.json automatically.
    """

    def __init__(self):
        self.private_key = None
        self.public_address = None

    def generate(self):
        """
        Generates a new private key and derives the public address.
        Saves to account.json and returns {privateKey, PublicAddress}.
        """
        # Generate random private key
        secret = randint(1, N - 1)
        priv = PrivateKey(secret=secret)

        # Derive public address (mainnet, compressed)
        address = priv.point.address(compressed=True, testnet=False)

        self.private_key = secret
        self.public_address = address

        account = {
            "privateKey": secret,
            "PublicAddress": address
        }

        # Save to account.json
        AccountDB().add_account(account)

        return account