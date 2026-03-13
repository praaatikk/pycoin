from Blockchain.Backend.util.util import decode_base58
from Blockchain.Backend.core.Script import Script
from Blockchain.Backend.core.Tx import TxIn, TxOut, Tx
from Blockchain.Backend.core.database.database import AccountDB
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey


class SendBTC:
    """
    Handles creating, signing, and preparing Bitcoin-like transactions
    in a local blockchain implementation.
    """

    def __init__(self, fromAccount, toAccount, Amount, UTXOS, blockchain=None):
        self.COIN = 100_000_000  # satoshis in 1 BTC
        self.FromPublicAddress = fromAccount
        self.toAccount = toAccount
        self.Amount = int(Amount * self.COIN)  # convert BTC to satoshis
        self.utxos = UTXOS
        self.blockchain = blockchain
        self.fee = int(0.0001 * self.COIN)  # fixed transaction fee
        self.isBalanceEnough = False
        self.reserved_utxos = {}

    # ----------------------------
    # Create a standard P2PKH scriptPubKey from address
    # ----------------------------
    def scriptPubKey(self, PublicAddress):
        h160 = decode_base58(PublicAddress)
        script_pubkey = Script().p2pkh_script(h160)
        return script_pubkey

    # ----------------------------
    # Safely get sender's private key from account DB
    # ----------------------------
    def getPrivateKey(self):
        accounts = AccountDB().read()
        if not accounts:
            print("No accounts found in account.json")
            return None

        for acc in accounts:
            if acc["PublicAddress"] == self.FromPublicAddress:
                return acc["privateKey"]

        print(f"No matching account found for {self.FromPublicAddress}")
        return None

    # ----------------------------
    # Select UTXOs to cover amount + fee
    # ----------------------------
    def prepareTxIn(self):
        TxIns = []
        self.Total = 0

        self.From_address_script_pubkey = self.scriptPubKey(self.FromPublicAddress)
        self.fromPubKeyHash = self.From_address_script_pubkey.cmds[2]

        newutxos = dict(self.utxos)

        for TxId, TxObj in newutxos.items():
            for index, txout in enumerate(TxObj.tx_outs):
                if txout is None:
                    continue
                if txout.script_pubkey.cmds[2] == self.fromPubKeyHash:
                    # FIX: normalize TxId to lowercase when creating TxIn
                    TxIns.append(TxIn(bytes.fromhex(TxObj.TxId.lower()), index))
                    self.Total += txout.amount
                    # FIX: normalize key to lowercase
                    self.reserved_utxos[(TxObj.TxId.lower(), index)] = txout

                    if self.Total >= self.Amount + self.fee:
                        break
            if self.Total >= self.Amount + self.fee:
                break

        if self.Total < self.Amount + self.fee:
            self.isBalanceEnough = False
            print("Insufficient balance for transaction + fee")
            return []

        self.isBalanceEnough = True
        return TxIns

    # ----------------------------
    # Prepare transaction outputs, including change back to sender
    # ----------------------------
    def prepareTxOut(self):
        TxOuts = []

        to_script = self.scriptPubKey(self.toAccount)
        TxOuts.append(TxOut(self.Amount, to_script))

        changeAmount = self.Total - self.Amount - self.fee

        if changeAmount > 0:
            TxOuts.append(TxOut(changeAmount, self.From_address_script_pubkey))

        return TxOuts

    # ----------------------------
    # Sign transaction inputs using sender's private key
    # ----------------------------
    def signTx(self):
        secret = self.getPrivateKey()
        if secret is None:
            print("Cannot sign transaction: private key not found")
            return

        priv = PrivateKey(secret=int(secret))

        for index, txin in enumerate(self.TxIns):
            self.TxObj.sign_input(index, priv, self.From_address_script_pubkey)

    # ----------------------------
    # Prepare full transaction object ready to broadcast or mine
    # ----------------------------
    def prepareTransaction(self):
        # Step 1: select inputs
        self.TxIns = self.prepareTxIn()
        if not self.isBalanceEnough:
            return False

        # Step 2: prepare outputs including change
        self.TxOuts = self.prepareTxOut()
        if not self.TxOuts:
            return False

        # Step 3: create Tx object
        self.TxObj = Tx(1, self.TxIns, self.TxOuts, 0)
        # FIX: normalize TxId to lowercase
        self.TxObj.TxId = self.TxObj.id().lower()

        # Step 4: sign transaction
        self.signTx()

        return self.TxObj

    # ----------------------------
    # Finalize transaction by marking UTXOs spent in blockchain
    # ----------------------------
    def finalizeTransaction(self):
        if not self.blockchain:
            return

        for prev_tx, index in self.reserved_utxos:
            # FIX: normalize to lowercase for lookup
            prev_tx_lower = prev_tx.lower()
            if prev_tx_lower in self.blockchain.utxos:
                self.blockchain.utxos[prev_tx_lower].tx_outs[index] = None