from ..abstract_test import AbstractTestContract, accounts, keys, TransactionFailed


class TestContract(AbstractTestContract):
    """
    run test with python -m unittest contracts.tests.do.test_dutch_auction
    """

    BACKER_1 = 1
    BACKER_2 = 2
    BLOCKS_PER_DAY = 5760
    TOTAL_TOKENS = 10000000 * 10**18
    WAITING_PERIOD = 60*60*24*7
    FUNDING_GOAL = 1250000

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
            self.pp.process('Wallets/MultiSigWalletWithDailyLimit.sol', add_dev_code=True, contract_dir=self.contract_dir),
            language='solidity',
            constructor_parameters=constructor_parameters
        )
        self.dutch_auction.setup(self.gnosis_token.address, self.multisig_wallet.address)
        # Start auction
        start_auction_data = self.dutch_auction.translator.encode('startAuction', [])
        self.multisig_wallet.submitTransaction(self.dutch_auction.address, 0, start_auction_data, sender=keys[wa_1])
        # Setups cannot be done twice
        self.assertRaises(TransactionFailed, self.dutch_auction.setup, self.gnosis_token.address)
        # Bidder 1 places a bid in the first block after auction starts
        self.assertEqual(self.dutch_auction.calcTokenPrice(), 20000 * 10**18 / 7500)
        bidder_1 = 0
        value_1 = 500000 * 10**18  # 500k Ether
        self.s.block.set_balance(accounts[bidder_1], value_1*2)
        self.dutch_auction.bid(sender=keys[bidder_1], value=value_1)
        self.assertEqual(self.dutch_auction.calcStopPrice(), value_1 / 9000000)
        # A few blocks later
        self.s.block.number += self.BLOCKS_PER_DAY*2
        self.assertEqual(self.dutch_auction.calcTokenPrice(), 20000 * 10**18 / (self.BLOCKS_PER_DAY*2 + 7500))
        # Stop price didn't change
        self.assertEqual(self.dutch_auction.calcStopPrice(), value_1 / 9000000)
        # Spender places a bid in the name of bidder 2
        bidder_2 = 1
        spender = 9
        value_2 = 500000 * 10**18  # 500k Ether
        self.s.block.set_balance(accounts[spender], value_2*2)
        self.dutch_auction.bid(accounts[bidder_2], sender=keys[spender], value=value_2)
        # Stop price changed
        self.assertEqual(self.dutch_auction.calcStopPrice(), (value_1 + value_2) / 9000000)
        # A few blocks later
        self.s.block.number += self.BLOCKS_PER_DAY*3
        self.assertEqual(self.dutch_auction.calcTokenPrice(), 20000 * 10 ** 18 / (self.BLOCKS_PER_DAY*5 + 7500))
        self.assertEqual(self.dutch_auction.calcStopPrice(), (value_1 + value_2) / 9000000)
        # Bidder 2 tries to send 0 bid
        self.assertRaises(TransactionFailed, self.dutch_auction.bid, sender=keys[bidder_2], value=0)
        # Bidder 3 places a bid
        bidder_3 = 2
        value_3 = 750000 * 10 ** 18  # 750k Ether
        self.s.block.set_balance(accounts[bidder_3], value_3*2)
        self.dutch_auction.bid(sender=keys[bidder_3], value=value_3)
        refund_bidder_3 = (value_1 + value_2 + value_3) - self.FUNDING_GOAL * 10**18
        # Bidder 3 gets refund; but paid gas so balance isn't exactly 0.75M Ether
        self.assertGreater(self.s.block.get_balance(accounts[bidder_3]), 0.98 * (value_3 + refund_bidder_3))
        self.assertEqual(self.dutch_auction.calcStopPrice(), (value_1 + value_2 + (value_3 - refund_bidder_3)) / 9000000)
        # Auction is over, no more bids are accepted
        self.assertRaises(TransactionFailed, self.dutch_auction.bid, sender=keys[bidder_3], value=value_3)
        self.assertEqual(self.dutch_auction.finalPrice(), self.dutch_auction.calcTokenPrice())
        # There is no money left in the contract
        self.assertEqual(self.s.block.get_balance(self.dutch_auction.address), 0)
        # Spender is triggering the claiming process for bidder 2
        self.dutch_auction.claimTokens(accounts[bidder_2], sender=keys[spender])
        # Bidder 3 claims his tokens
        self.dutch_auction.claimTokens(sender=keys[bidder_3])
        # Confirm token balances
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_2]),
                         value_2 * 10 ** 18 / self.dutch_auction.finalPrice())
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_3]),
                         (value_3 - refund_bidder_3) * 10 ** 18 / self.dutch_auction.finalPrice())
        self.assertEqual(self.gnosis_token.balanceOf(self.multisig_wallet.address),
                         self.TOTAL_TOKENS - self.dutch_auction.totalReceived() * 10 ** 18 / self.dutch_auction.finalPrice())
        self.assertEqual(self.gnosis_token.totalSupply(), self.TOTAL_TOKENS)
        self.assertEqual(self.dutch_auction.totalReceived() / 1e18, self.FUNDING_GOAL)
        # Auction ended but trading is not possible yet, because there is one week pause after auction ends
        transfer_shares = 1000
        bidder_4 = 3
        self.assertRaises(TransactionFailed, self.gnosis_token.transfer, accounts[bidder_4], transfer_shares, sender=keys[bidder_3])
        # We wait for one week
        self.s.block.timestamp += self.WAITING_PERIOD
        self.assertRaises(TransactionFailed, self.gnosis_token.transfer, accounts[bidder_4], transfer_shares, sender=keys[bidder_3])
        # Go past one week
        self.s.block.timestamp += 1
        # Token is launched
        self.assertTrue(self.dutch_auction.tokenLaunched())
        # Bidder 1 claim his tokens after the waiting period is over
        self.dutch_auction.claimTokens(sender=keys[bidder_1])
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_1]),
                         value_1 * 10 ** 18 / self.dutch_auction.finalPrice())
        # Shares can be traded now. Backer 3 transfers 1000 shares to backer 4.
        self.assertTrue(self.gnosis_token.transfer(accounts[bidder_4], transfer_shares, sender=keys[bidder_3]))
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_4]), transfer_shares)
        # Also transferFrom works now.
        self.assertTrue(self.gnosis_token.approve(accounts[bidder_3], transfer_shares, sender=keys[bidder_4]))
        self.assertTrue(
            self.gnosis_token.transferFrom(accounts[bidder_4], accounts[bidder_3], transfer_shares, sender=keys[bidder_3]))
        self.assertEqual(self.gnosis_token.balanceOf(accounts[bidder_4]), 0)
