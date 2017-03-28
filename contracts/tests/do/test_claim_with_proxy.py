from ..abstract_test import AbstractTestContract, accounts, keys


class TestContract(AbstractTestContract):
    """
    run test with python -m unittest contracts.tests.do.test_claim_with_proxy
    """

    BACKER_1 = 1
    BACKER_2 = 2
    BLOCKS_PER_DAY = 5760
    TOTAL_TOKENS = 10000000 * 10**18
    MAX_TOKENS_SOLD = 9000000 * 10**18
    PREASSIGNED_TOKENS = 1000000 * 10**18
    WAITING_PERIOD = 60*60*24*7
    MAX_GAS = 150000  # Kraken gas limit
    FUNDING_GOAL = 250000 * 10**18
    START_PRICE_FACTOR = 4000

    def __init__(self, *args, **kwargs):
        super(TestContract, self).__init__(*args, **kwargs)
        self.deploy_contracts = [self.gnosis_token_name, self.dutch_auction_name]

    def test(self):
        # Create wallet
        required_accounts = 1
        wa_1 = 1
        constructor_parameters = (
            [accounts[wa_1]],
            required_accounts
        )
        self.multisig_wallet = self.s.abi_contract(
            self.pp.process(self.WALLETS_DIR + 'MultiSigWalletWithDailyLimit.sol', add_dev_code=True,
                            contract_dir=self.contract_dir),
            language='solidity',
            constructor_parameters=constructor_parameters
        )
        # Create dutch auction
        self.dutch_auction.setup(self.gnosis_token.address,
                                 self.multisig_wallet.address,
                                 [self.multisig_wallet.address],
                                 [self.PREASSIGNED_TOKENS])
        #
        self.claim_proxy = self.s.abi_contract(
            self.pp.process(self.DO_DIR + 'ClaimProxy.sol', add_dev_code=True,
                            contract_dir=self.contract_dir),
            language='solidity',
            constructor_parameters=[self.dutch_auction.address]
        )
        # Set funding goal
        change_ceiling_data = self.dutch_auction.translator.encode('changeCeiling',
                                                                   [self.FUNDING_GOAL, self.START_PRICE_FACTOR])
        self.multisig_wallet.submitTransaction(self.dutch_auction.address, 0, change_ceiling_data, sender=keys[wa_1])
        # Start auction
        start_auction_data = self.dutch_auction.translator.encode('startAuction', [])
        self.multisig_wallet.submitTransaction(self.dutch_auction.address, 0, start_auction_data, sender=keys[wa_1])
        # Bidder 1 places a bid in the first block after auction starts
        bidder_1 = 0
        value_1 = 100000 * 10**18  # 100k Ether
        self.s.block.set_balance(accounts[bidder_1], value_1*2)
        self.dutch_auction.bid(sender=keys[bidder_1], value=value_1)
        # A few blocks later
        self.s.block.number += self.BLOCKS_PER_DAY*2
        # Spender places a bid in the name of bidder 2
        bidder_2 = 1
        spender = 9
        value_2 = 100000 * 10**18  # 100k Ether
        self.s.block.set_balance(accounts[spender], value_2*2)
        self.dutch_auction.bid(accounts[bidder_2], sender=keys[spender], value=value_2)
        # A few blocks later
        self.s.block.number += self.BLOCKS_PER_DAY*3
        # Bidder 3 places a bid
        bidder_3 = 2
        value_3 = 100000 * 10 ** 18  # 100k Ether
        self.s.block.set_balance(accounts[bidder_3], value_3*2)
        profiling = self.dutch_auction.bid(sender=keys[bidder_3], value=value_3, profiling=True)
        self.assertLessEqual(profiling['gas'], self.MAX_GAS)
        refund_bidder_3 = (value_1 + value_2 + value_3) - self.FUNDING_GOAL
        # Claim all tokens via proxy
        self.claim_proxy.claimTokensFor([accounts[bidder_1], accounts[bidder_2], accounts[bidder_3]])
        # Confirm token balances
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_2]),
                         value_2 * 10 ** 18 / self.dutch_auction.finalPrice())
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_3]),
                         (value_3 - refund_bidder_3) * 10 ** 18 / self.dutch_auction.finalPrice())
        self.assertEqual(self.gnosis_token.balanceOf(self.multisig_wallet.address),
                         self.PREASSIGNED_TOKENS + (
                             self.MAX_TOKENS_SOLD - self.dutch_auction.totalReceived() * 10 ** 18
                             / self.dutch_auction.finalPrice()))
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_1]),
                         value_1 * 10 ** 18 / self.dutch_auction.finalPrice())
