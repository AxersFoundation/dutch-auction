pragma solidity 0.4.11;
import "Oracles/AbstractOracle.sol";


/// @title Signed message oracle contract - Allows to set an outcome with a signed message.
/// @author Stefan George - <stefan@gnosis.pm>
contract SignedMessageOracle is Oracle {

    /*
     *  Storage
     */
    address oracle;
    address replacement;
    bool isSet;
    int outcome;

    /*
     *  Public functions
     */
    /// @dev Constructor sets oracle address based on signature.
    /// @param descriptionHash Hash identifying off chain event description.
    /// @param v Signature parameter.
    /// @param r Signature parameter.
    /// @param s Signature parameter.
    function SignedMessageOracle(bytes32 descriptionHash, uint8 v, bytes32 r, bytes32 s)
        public
    {
        oracle = ecrecover(descriptionHash, v, r, s);
    }

    /// @dev Replaces oracle/signing private key for an oracle.
    /// @param _oracle New oracle.
    function replaceOracle(address _oracle)
        public
    {
        if (isSet || msg.sender != oracle)
            // Result was set already or sender is not registered oracle
            revert();
        replacement = _oracle;
    }

    /// @dev Sets outcome based on signed message.
    /// @param descriptionHash Hash identifying off chain event description.
    /// @param outcome Signed event outcome.
    /// @param v Signature parameter.
    /// @param r Signature parameter.
    /// @param s Signature parameter.
    function setOutcome(bytes32 descriptionHash, int outcome, uint8 v, bytes32 r, bytes32 s)
        public
    {
        address _oracle = ecrecover(keccak256(descriptionHash, outcome), v, r, s);
        if (isSet || _oracle != oracle)
            // Result was set already or result was not signed by registered oracle
            revert();
        isSet = true;
        outcome = outcome;
    }

    /// @dev Returns if winning outcome is set for given event.
    /// @return Returns if outcome is set.
    function isOutcomeSet()
        public
        constant
        returns (bool)
    {
        if (replacement == 0)
            return isSet;
        return Oracle(replacement).isOutcomeSet();
    }

    /// @dev Returns winning outcome for given event.
    /// @return Returns outcome.
    function getOutcome()
        public
        constant
        returns (int)
    {
        return outcome;
    }
}