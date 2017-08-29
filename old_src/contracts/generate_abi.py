from ethereum.tester import languages
from preprocessor import PreProcessor
import json

pp = PreProcessor()
contracts = ['DO/DutchAuction.sol',
             'Tokens/GnosisToken.sol',
             'DO/ClaimProxy.sol',
             'DO/Disbursement.sol']
contract_dir = 'solidity/'

for contract_name in contracts:
    code = pp.process(contract_name, add_dev_code=False, contract_dir=contract_dir, replace_unknown_addresses=True)
    compiled = languages["solidity"].combined(code)[-1][1]
    # save abi
    file_name = contract_name.split(".")[0].split("/")[-1]
    h = open("abi/{}.json".format(file_name), "w+")
    h.write(json.dumps(compiled["abi"]))
    h.close()
    print '{} ABI generated.'.format(file_name)
