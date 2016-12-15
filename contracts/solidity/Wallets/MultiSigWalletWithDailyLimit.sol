pragma solidity 0.4.4;
import "Wallets/MultiSigWallet.sol";


/// @title Multisignature wallet with daily limit - Allows an owner to withdraw a daily limit without multisig.
/// @author Stefan George - <stefan.george@consensys.net>
contract MultiSigWalletWithDailyLimit is MultiSigWallet {

    event DailyLimitChange(uint dailyLimit);

    uint public dailyLimit;
    uint public lastDay;
    uint public spentToday;

    /*
     * Public functions
     */
    /// @dev Contract constructor sets initial owners, required number of confirmations and daily withdraw limit.
    /// @param _owners List of initial owners.
    /// @param _required Number of required confirmations.
    /// @param _dailyLimit Amount in wei, which can be withdrawn without confirmations on a daily basis.
    function MultiSigWalletWithDailyLimit(address[] _owners, uint _required, uint _dailyLimit)
        public
        MultiSigWallet(_owners, _required)
    {
        dailyLimit = _dailyLimit;
    }

    /// @dev Allows to change the daily limit. Transaction has to be sent by wallet.
    /// @param _dailyLimit Amount in wei.
    function changeDailyLimit(uint _dailyLimit)
        public
        onlyWallet
    {
        dailyLimit = _dailyLimit;
        DailyLimitChange(_dailyLimit);
    }

    /// @dev Allows anyone to execute a confirmed transaction or ether withdraws until daily limit is reached.
    /// @param transactionHash Hash identifying a transaction.
    function executeTransaction(bytes32 transactionHash)
        public
        notExecuted(transactionHash)
    {
        Transaction tx = transactions[transactionHash];
        if (isConfirmed(transactionHash) || tx.data.length == 0 && underLimit(tx.value)) {
            tx.executed = true;
            if (tx.destination.call.value(tx.value)(tx.data))
                Execution(transactionHash);
            else {
                ExecutionFailure(transactionHash);
                tx.executed = false;
            }
        }
    }

    /*
     * Internal functions
     */
    /// @dev Returns if amount is within daily limit and updates daily spending.
    /// @param amount Amount to withdraw.
    /// @return Returns if amount is under daily limit.
    function underLimit(uint amount)
        internal
        returns (bool)
    {
        if (now > lastDay + 24 hours) {
            lastDay = now;
            spentToday = 0;
        }
        if (spentToday + amount > dailyLimit || amount > dailyLimit)
            return false;
        spentToday += amount;
        return true;
    }
}
