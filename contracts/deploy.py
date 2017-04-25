from ethjsonrpc import EthJsonRpc
from ethereum.tester import languages
from ethereum import tester as t
from ethereum.abi import ContractTranslator
from ethereum.transactions import Transaction
from ethereum.utils import privtoaddr
from preprocessor import PreProcessor
import click
import time
import json
import rlp
import logging
logging.basicConfig(level=logging.INFO)


class Deploy:

    def __init__(self, protocol, host, port, add_dev_code, verify_code, optimize, contract_dir, gas, gas_price, private_key):
        self.pp = PreProcessor()
        self.s = t.state()
        self.s.block.number = 1150000  # Homestead
        t.gas_limit = int(gas)
        self.json_rpc = EthJsonRpc(protocol=protocol, host=host, port=port)
        if private_key:
            self.user_address = '0x' + privtoaddr(private_key.decode('hex')).encode('hex')
        else:
            self.user_address = self.json_rpc.eth_coinbase()["result"]
        self.add_dev_code = add_dev_code == 'true'
        self.verify_code = verify_code == 'true'
        self.optimize = optimize == 'true'
        self.contract_dir = contract_dir
        self.gas = int(gas)
        self.gas_price = int(gas_price)
        self.private_key = private_key
        self.contract_addresses = {}
        self.contract_abis = {}

    def wait_for_transaction_receipt(self, transaction_hash):
        while self.json_rpc.eth_getTransactionReceipt(transaction_hash)['result'] is None:
            logging.info('Waiting for transaction receipt {}'.format(transaction_hash))
            time.sleep(5)

    def replace_address(self, a):
        if isinstance(a, list):
            return [self.replace_address(i) for i in a]
        else:
            return self.contract_addresses[a] if isinstance(a, basestring) and a in self.contract_addresses else a

    def get_nonce(self):
        return int(self.json_rpc.eth_getTransactionCount(self.user_address, default_block="pending")["result"][2:], 16)

    def get_raw_transaction(self, data, contract_address=''):
        nonce = self.get_nonce()
        tx = Transaction(nonce, self.gas_price, self.gas, contract_address, 0, data.decode('hex'))
        tx.sign(self.private_key.decode('hex'))
        return rlp.encode(tx).encode('hex')

    def code_is_valid(self, contract_address, compiled_code):
        deployed_code = self.json_rpc.eth_getCode(contract_address)["result"]
        locally_deployed_code_address = self.s.evm(compiled_code.decode("hex")).encode("hex")
        locally_deployed_code = self.s.block.get_code(locally_deployed_code_address).encode("hex")
        return deployed_code == "0x" + locally_deployed_code

    def compile_code(self, code, language):
        combined = languages[language].combined(code, optimize=self.optimize)
        compiled_code = combined[-1][1]["bin_hex"]
        abi = combined[-1][1]["abi"]
        return compiled_code, abi

    @staticmethod
    def replace_library_placeholders(bytecode, addresses):
        if addresses:
            for library_name, library_address in addresses.iteritems():
                bytecode = bytecode.replace("__{}{}".format(library_name, "_" * (38 - len(library_name))), library_address[2:])
        return bytecode

    def deploy_code(self, file_path, reference, params, addresses):
        if addresses:
            addresses = dict([(k, self.replace_address(v)) for k, v in addresses.iteritems()])
        language = "solidity" if file_path.endswith(".sol") else "serpent"
        code = self.pp.process(file_path,
                               add_dev_code=self.add_dev_code,
                               contract_dir=self.contract_dir,
                               addresses=addresses)
        # compile code
        bytecode, abi = self.compile_code(code, language)
        # replace library placeholders
        bytecode = self.replace_library_placeholders(bytecode, addresses)
        if params:
            translator = ContractTranslator(abi)
            # replace constructor placeholders
            params = [self.replace_address(p) for p in params]
            bytecode += translator.encode_constructor_arguments(params).encode("hex")
        logging.info('Try to create contract with length {} based on code in file: {}'.format(len(bytecode),
                                                                                              file_path))
        if self.private_key:
            raw_tx = self.get_raw_transaction(bytecode)
            tx_response = self.json_rpc.eth_sendRawTransaction("0x" + raw_tx)
            while "error" in tx_response:
                logging.info('Deploy failed with error {}. Retry!'.format(tx_response['error']))
                time.sleep(5)
                tx_response = self.json_rpc.eth_sendRawTransaction("0x" + raw_tx)
        else:
            tx_response = self.json_rpc.eth_sendTransaction(self.user_address, data=bytecode, gas=self.gas,
                                                            gas_price=self.gas_price)
            while "error" in tx_response:
                logging.info('Deploy failed with error {}. Retry!'.format(tx_response['error']))
                time.sleep(5)
                tx_response = self.json_rpc.eth_sendTransaction(self.user_address, data=bytecode, gas=self.gas,
                                                                gas_price=self.gas_price)
        transaction_hash = tx_response['result']
        self.wait_for_transaction_receipt(transaction_hash)
        contract_address = self.json_rpc.eth_getTransactionReceipt(transaction_hash)["result"]["contractAddress"]
        # Verify deployed code with locally deployed code
        if self.verify_code and not self.code_is_valid(contract_address, bytecode):
            logging.info('Deploy of {} failed. Retry!'.format(file_path))
            self.deploy_code(file_path, params, addresses)
        if reference:
            contract_name = reference
        else:
            contract_name = file_path.split("/")[-1].split(".")[0]
        self.contract_addresses[contract_name] = contract_address
        self.contract_abis[contract_name] = abi
        logging.info('Contract {} was created at address {}.'.format(reference if reference else file_path, contract_address))

    def send_transaction(self, contract, name, params, abi):
        contract_address = self.replace_address(contract)
        contract_abi = self.contract_abis[contract] if contract in self.contract_abis else [abi]
        if not name:
            name = abi["name"]
        translator = ContractTranslator(contract_abi)
        data = translator.encode(name, self.replace_address(params)).encode("hex")
        logging.info('Try to send {} transaction to contract {}.'.format(name, contract))
        if self.private_key:
            raw_tx = self.get_raw_transaction(data, contract_address)
            tx_response = self.json_rpc.eth_sendRawTransaction("0x" + raw_tx)
            while 'error' in tx_response:
                logging.info('Transaction failed with error {}. Retry!'.format(tx_response['error']))
                time.sleep(5)
                tx_response = self.json_rpc.eth_sendRawTransaction("0x" + raw_tx)
        else:
            tx_response = self.json_rpc.eth_sendTransaction(self.user_address, to_address=contract_address, data=data,
                                                            gas=self.gas, gas_price=self.gas_price)
            while 'error' in tx_response:
                logging.info('Transaction failed with error {}. Retry!'.format(tx_response['error']))
                time.sleep(5)
                tx_response = self.json_rpc.eth_sendTransaction(self.user_address, to_address=contract_address,
                                                                data=data, gas=self.gas, gas_price=self.gas_price)
        transaction_hash = tx_response['result']
        self.wait_for_transaction_receipt(transaction_hash)
        logging.info('Transaction {} for contract {} completed.'.format(name, contract))

    @staticmethod
    def strip_0x(string):
        if string.startswith("0x"):
            return string[2:]
        return string

    def assert_call(self, contract, name, params, return_value):
        contract_address = self.replace_address(contract)
        return_value = self.replace_address(return_value)
        contract_abi = self.contract_abis[contract]
        translator = ContractTranslator(contract_abi)
        data = "0x" + translator.encode(name, [self.replace_address(p) for p in params]).encode("hex")
        logging.info('Try to assert return value of {} in contract {}.'.format(name, contract))
        response = self.json_rpc.eth_call(from_address=self.user_address, to_address=contract_address, data=data)
        bc_return_val = response["result"]
        result_decoded = translator.decode(name, bc_return_val[2:].decode("hex"))
        result_decoded = result_decoded if len(result_decoded) > 1 else result_decoded[0]
        if isinstance(return_value, int) or isinstance(return_value, long):
            assert result_decoded == return_value
        else:
            assert result_decoded.lower() == self.strip_0x(return_value.lower())
        logging.info('Assertion successful for return value of {} in contract {}.'.format(name, contract))

    def process(self, f):
        with open(f) as data_file:
            instructions = json.load(data_file)
            logging.info('Your address: {}'.format(self.user_address))
            for instruction in instructions:
                logging.info('Your balance: {} Wei'.format(
                    int(self.json_rpc.eth_getBalance(self.user_address)['result'], 16)))
                if instruction["type"] == "deployment":
                    self.deploy_code(
                        instruction["file"],
                        instruction["reference"] if "reference" in instruction else None,
                        instruction["params"] if "params" in instruction else None,
                        instruction["addresses"] if "addresses" in instruction else None,
                    )
                elif instruction["type"] == "transaction":
                    self.send_transaction(
                        instruction["contract"],
                        instruction["name"] if "name" in instruction else None,
                        instruction["params"] if "params" in instruction else [],
                        instruction["abi"] if "abi" in instruction else None
                    )
                elif instruction["type"] == "assertion":
                    self.assert_call(
                        instruction["contract"],
                        instruction["name"],
                        instruction["params"] if "params" in instruction else [],
                        instruction["return"]
                    )
            for contract_name, contract_address in self.contract_addresses.iteritems():
                logging.info('Contract {} was created at address {}.'.format(contract_name, contract_address))


@click.command()
@click.option('-f', help='File with instructions')
@click.option('-protocol', default="http", help='Ethereum server protocol')
@click.option('-host', default="localhost", help='Ethereum server host')
@click.option('-port', default='8545', help='Ethereum server port')
@click.option('-add_dev_code', default='false', help='Add admin methods')
@click.option('-verify_code', default='false', help='Verify code deployments with test deployment')
@click.option('-optimize', default='false', help='Use the solidity optimizer to compile code')
@click.option('-contract_dir', default='solidity/', help='Import directory')
@click.option('-gas', default='4712388', help='Transaction gas')
@click.option('-gas_price', default='20000000000', help='Transaction gas price')
@click.option('-private_key', help='Private key as hex to sign transactions')
def setup(f, protocol, host, port, add_dev_code, verify_code, optimize, contract_dir, gas, gas_price, private_key):
    deploy = Deploy(protocol, host, port, add_dev_code, verify_code, optimize, contract_dir, gas, gas_price, private_key)
    deploy.process(f)

if __name__ == '__main__':
    setup()
