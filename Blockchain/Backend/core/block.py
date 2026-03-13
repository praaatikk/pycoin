class Block:
    """
    Block is a storage container that stores transactions
    """

    def __init__(self, Height, Blocksize, BlockHeader, TxCount, Txs, Fee=0):
        self.Height = Height
        self.Blocksize = Blocksize
        self.BlockHeader = BlockHeader
        self.Txcount = TxCount
        self.Txs = Txs
        self.Fee = Fee  # FIX: store fee collected in this block (in satoshis)