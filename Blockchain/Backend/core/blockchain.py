# python -m Blockchain.Backend.core.blockchain

import sys
sys.path.append("/Users/Vmaha/Desktop/Bitcoin")

from Blockchain.Backend.core.database.database import AccountDB, BlockchainDB
from Blockchain.Backend.util.util import decode_base58, merkle_root, target_to_bits
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.Tx import CoinbaseTx, Tx, TxIn, TxOut
from Blockchain.Backend.core.Script import Script
from Blockchain.Frontend.run import main  # Flask frontend
from threading import Thread, Lock as ThreadLock
import time
import copy
from multiprocessing import Lock

disk_lock = Lock()
mining_lock = ThreadLock()

ZERO_HASH = "0" * 64
VERSION = 1

INITIAL_TARGET = 0x0000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF


class Blockchain:
    def __init__(self, utxos, MemPool):
        self.utxos = utxos
        self.MemPool = MemPool
        self.current_target = INITIAL_TARGET
        self.bits = target_to_bits(INITIAL_TARGET)
        self.rebuild_utxos()

    # -------------------------
    # REBUILD UTXOS FROM DISK
    # -------------------------
    def rebuild_utxos(self):
        blockchainDB = BlockchainDB()
        blocks = blockchainDB.read()
        self.utxos.clear()

        for block in blocks:
            for tx_data in block["Txs"]:
                tx_ins = [TxIn(bytes.fromhex(tx_in["prev_tx"]), tx_in["prev_index"])
                          for tx_in in tx_data["tx_ins"]]

                tx_outs = []
                for tx_out in tx_data["tx_outs"]:
                    rebuilt_cmds = [
                        bytes.fromhex(cmd) if isinstance(cmd, str) else cmd
                        for cmd in tx_out["script_pubkey"]["cmds"]
                    ]
                    tx_outs.append(TxOut(tx_out["amount"], Script(rebuilt_cmds)))

                tx_obj = Tx(tx_data["version"], tx_ins, tx_outs, tx_data["locktime"])
                tx_obj.TxId = tx_data["TxId"]

                for tx_in in tx_ins:
                    if tx_in.prev_tx == b'\x00' * 32:
                        continue
                    prev = tx_in.prev_tx.hex().lower()
                    index = tx_in.prev_index
                    if prev in self.utxos:
                        prev_tx_obj = self.utxos[prev]
                        if index < len(prev_tx_obj.tx_outs):
                            prev_tx_obj.tx_outs[index] = None
                        if all(out is None for out in prev_tx_obj.tx_outs):
                            del self.utxos[prev]

                self.utxos[tx_obj.TxId.lower()] = tx_obj

    # -------------------------
    # GET BALANCE
    # -------------------------
    def get_balance(self, address):
        balance = 0
        h160 = decode_base58(address)

        for tx in self.utxos.values():
            for tx_out in tx.tx_outs:
                if tx_out is None:
                    continue
                if tx_out.script_pubkey.cmds[2] == h160:
                    balance += tx_out.amount

        return balance / 100000000

    # -------------------------
    # GET ALL ACCOUNTS WITH BALANCE
    # -------------------------
    def get_all_accounts_with_balance(self):
        """
        Returns all accounts from account.json with their current balance.
        """
        accounts = AccountDB().read()
        result = []

        for acc in accounts:
            balance = self.get_balance(acc["PublicAddress"])
            result.append({
                "privateKey": acc["privateKey"],
                "PublicAddress": acc["PublicAddress"],
                "balance": balance
            })

        return result

    # -------------------------
    # GET TRANSACTION HISTORY FOR ADDRESS
    # -------------------------
    def get_transaction_history(self, address):
        history = []
        h160 = decode_base58(address)
        blockchainDB = BlockchainDB()
        blocks = blockchainDB.read()

        for block in blocks:
            for tx_data in block["Txs"]:
                sent = 0
                received = 0
                involved = False

                for tx_out in tx_data["tx_outs"]:
                    cmds = tx_out["script_pubkey"]["cmds"]
                    if len(cmds) > 2 and isinstance(cmds[2], str):
                        if bytes.fromhex(cmds[2]) == h160:
                            received += tx_out["amount"]
                            involved = True

                for tx_in in tx_data["tx_ins"]:
                    prev_txid = tx_in["prev_tx"].lower()
                    prev_index = tx_in["prev_index"]
                    if prev_txid in self.utxos:
                        prev_tx_obj = self.utxos[prev_txid]
                        if prev_index < len(prev_tx_obj.tx_outs):
                            out = prev_tx_obj.tx_outs[prev_index]
                            if out and out.script_pubkey.cmds[2] == h160:
                                sent += out.amount
                                involved = True

                if involved:
                    history.append({
                        "block_height": block["Height"],
                        "txid": tx_data["TxId"],
                        "sent": sent / 100000000,
                        "received": received / 100000000,
                        "fee": block.get("Fee", 0) / 100000000,
                    })

        return history[::-1]

    # -------------------------
    # WRITE TO DISK
    # -------------------------
    def write_on_disk(self, block):
        with disk_lock:
            BlockchainDB().write(block)
            print(f"Block {block[0]['Height']} written to blockchain.json")

    # -------------------------
    # MEMORY POOL HANDLING
    # -------------------------
    def read_transaction_from_memorypool(self):
        self.Blocksize = 80
        self.TxIds = []
        self.addTransactionsInBlock = []
        self.remove_spent_transactions = []

        for txid, tx in self.MemPool.items():
            self.TxIds.append(bytes.fromhex(txid))
            self.addTransactionsInBlock.append(tx)
            self.Blocksize += len(tx.serialize())
            for spent in tx.tx_ins:
                self.remove_spent_transactions.append([spent.prev_tx, spent.prev_index])

    def remove_transactions_from_memorypool(self):
        for tx in self.addTransactionsInBlock:
            if tx.TxId in self.MemPool:
                del self.MemPool[tx.TxId]

    # -------------------------
    # UTXO UPDATE
    # -------------------------
    def update_utxos(self):
        for prev_tx, index in self.remove_spent_transactions:
            prev_tx_hex = prev_tx.hex().lower()
            if prev_tx_hex in self.utxos:
                tx = self.utxos[prev_tx_hex]
                if index < len(tx.tx_outs):
                    tx.tx_outs[index] = None
                if all(out is None for out in tx.tx_outs):
                    del self.utxos[prev_tx_hex]

        for tx in self.addTransactionsInBlock:
            self.utxos[tx.TxId.lower()] = tx

    # -------------------------
    # CONVERT TRANSACTIONS TO JSON
    # -------------------------
    def convert_to_json(self):
        self.TxJson = []
        for tx in self.addTransactionsInBlock:
            tx_copy = copy.deepcopy(tx)
            tx_copy.tx_outs = [out for out in tx_copy.tx_outs if out is not None]
            self.TxJson.append(tx_copy.to_dict())

    # -------------------------
    # CALCULATE FEE
    # -------------------------
    def calculate_fee(self):
        input_amount = 0
        output_amount = 0

        for prev_tx, index in self.remove_spent_transactions:
            prev_hex = prev_tx.hex().lower()
            if prev_hex in self.utxos and self.utxos[prev_hex].tx_outs[index]:
                input_amount += self.utxos[prev_hex].tx_outs[index].amount

        for tx in self.addTransactionsInBlock:
            for tx_out in tx.tx_outs:
                output_amount += tx_out.amount

        self.fee = input_amount - output_amount

    # -------------------------
    # ADD BLOCK
    # -------------------------
    def addBlock(self, BlockHeight, prevBlockHash, miner_address):
        with mining_lock:
            self.read_transaction_from_memorypool()
            self.calculate_fee()

            timestamp = int(time.time())

            coinbaseTx = CoinbaseTx(BlockHeight, miner_address).CoinbaseTransaction()
            coinbaseTx.tx_outs[0].amount += self.fee

            self.TxIds.insert(0, bytes.fromhex(coinbaseTx.id()))
            self.addTransactionsInBlock.insert(0, coinbaseTx)

            merkleRoot = merkle_root(self.TxIds)[::-1].hex()

            blockheader = BlockHeader(
                VERSION, prevBlockHash, merkleRoot, timestamp, self.bits
            )
            blockheader.mine(self.current_target)

            self.update_utxos()
            self.remove_transactions_from_memorypool()
            self.convert_to_json()

            if self.fee > 0:
                print(f"Block {BlockHeight} mined successfully | Fee: {self.fee / 100000000:.8f} BTC")
            else:
                print(f"Block {BlockHeight} mined successfully")

            self.write_on_disk(
                [
                    Block(
                        BlockHeight,
                        self.Blocksize,
                        blockheader.__dict__,
                        len(self.TxJson),
                        self.TxJson,
                        self.fee,
                    ).__dict__
                ]
            )

    # -------------------------
    # FETCH LAST BLOCK
    # -------------------------
    def fetch_last_block(self):
        return BlockchainDB().lastBlock()

    # -------------------------
    # GENESIS BLOCK
    # -------------------------
    def GenesisBlock(self, miner_address):
        print("Mining Genesis Block...")
        self.addBlock(0, ZERO_HASH, miner_address)

    # -------------------------
    # MINING LOOP
    # -------------------------
    def main(self, miner_address):
        lastBlock = self.fetch_last_block()
        if lastBlock is None:
            self.GenesisBlock(miner_address)

        while True:
            # Wait 10 seconds before starting next block cycle
            time.sleep(10)

            lastBlock = self.fetch_last_block()
            BlockHeight = lastBlock["Height"] + 1
            prevBlockHash = lastBlock["BlockHeader"]["blockHash"]

            # FIX: if mempool is empty, wait up to 30 more seconds
            # checking every 2 seconds for incoming transactions
            if not self.MemPool:
                print(f"Waiting for transactions... (Block {BlockHeight} ready)")
                waited = 0
                while not self.MemPool and waited < 30:
                    time.sleep(2)
                    waited += 2

            if self.MemPool:
                print(f"Mining Block {BlockHeight} with {len(self.MemPool)} mempool tx(s)...")
            else:
                print(f"Mining Block {BlockHeight} (no transactions)...")

            self.addBlock(BlockHeight, prevBlockHash, miner_address)


# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    utxos = {}
    MemPool = {}

    blockchain = Blockchain(utxos, MemPool)

    accounts = AccountDB().read()
    miner_address = accounts[-1]["PublicAddress"]

    mining_thread = Thread(target=blockchain.main, args=(miner_address,), daemon=True)
    mining_thread.start()

    main(utxos, MemPool, blockchain)

    print("Mining reward going to:", miner_address)