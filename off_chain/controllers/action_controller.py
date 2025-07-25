import os
import json
import sys
from colorama import init, Fore, Style
init(strip=False, convert=False)
from controllers.deploy_controller import DeployController
from session.logging import log_msg, log_error
from web3 import Web3
from config.web3_provider import get_web3
import getpass
import re
from types import SimpleNamespace as FailedReceipt






class ActionController:
    """
    This class implements the ActionController for managing actions on the Carbon Credit Management System.
    It provides methods for loading the contract, deploying and initializing it, reading and writing data,
    listening to events, and handling user actions such as adding users, updating user information,
    adding and removing tokens, transferring tokens, registering operations, and checking balances.
    It also includes methods for grouping user operations by date and listening to specific events.
    """

    def __init__(self):
        
        self.w3 = get_web3()
        self.contract = None


    def load_contract(self):
        """
        Loads the contract from the specified path and initializes it.
        Returns:
            bool: True if the contract is loaded successfully, False otherwise.
        """

        if os.path.exists("on_chain/contract_address.txt"):
         try:
            address = open('on_chain/contract_address.txt').read().strip()
            code = self.w3.eth.get_code(address)
            if not code or code == b'\x00' or code.hex() == '0x':
                return False  
            abi = json.load(open('on_chain/contract_abi.json'))
            self.contract = self.w3.eth.contract(address=address, abi=abi)
            return True

         except Exception as e:
            log_error(f"Errore caricamento contratto: {e}")
            print(Fore.RED + f"Errore caricamento contratto: {e}" + Style.RESET_ALL)
            self.contract = None
            return False 
        else:
            print("The contract has not yet been deployed.")
        return False


    def deploy_and_initialize(self, source_path='../../on_chain/CarbonCreditRecords.sol'):
        """
        Deploys the contract and initializes it.

        Args:
            source_path (str): The path to the Solidity source file.
        """
        print("Starting deployment and contract initialization...")
        controller = DeployController()
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), source_path))

        while True:
            try:
                controller.compile_and_deploy(path)
                self.contract = controller.contract
                os.makedirs('on_chain', exist_ok=True)

                with open('on_chain/contract_address.txt', 'w') as f:
                    f.write(self.contract.address)

                with open('on_chain/contract_abi.json', 'w') as f:
                    json.dump(self.contract.abi, f)

                print("Deploy and initialization completed successfully.")
                break

            except Exception as e:
                print(f"Deploy failed: {e}")
                
                while True:
                    choice = input("Do you want to retry? (Y = Yes / N = No): ").strip().upper()
                    if choice == 'Y':
                        break  
                    elif choice == 'N':
                        print("Exiting...")
                        sys.exit(1)
                    else:
                        print("Invalid input. Please enter 'Y' or 'N'.")  


    def write_data_user(self, function_name, *args): 
        """
        Inert user data to a contract's function. The action is performed by the admin.

        Args:
            function_name (str): The function name to call on the contract.
            *args: Arguments required by the function.

        Returns:
            The transaction receipt object.
        """
        
        try:
                private_key = os.getenv('ADMIN_PRIVATE_KEY')
                function = getattr(self.contract.functions, function_name)(*args)
                gas_estimate = function.estimate_gas({'from': os.getenv('ADMIN_ADDRESS')})
           
                transaction = function.build_transaction({
                'from': os.getenv('ADMIN_ADDRESS'),
                'nonce': self.w3.eth.get_transaction_count(os.getenv('ADMIN_ADDRESS')),
                'gas': int(gas_estimate),
                'gasPrice': self.w3.eth.gas_price
                })
                
                signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key=private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                log_msg(f"Transaction {function_name} executed. From: {os.getenv('ADMIN_ADDRESS')}, Tx Hash: {tx_hash.hex()}, Gas: {gas_estimate}, Gas Price: {self.w3.eth.gas_price}")
                
                return receipt

        except Exception as e:
                log_error(f"Error executing registration. Error: {str(e)}")
                raise e
        
        
    def write_data(self, function_name, from_address, *args):
        """
        Writes data to a contract's function. It is used for: updating user information, transferring tokens, 
        registering operations, and registering green actions.

        Args:
            function_name (str): The function name to call on the contract.
            from_address (str): The Ethereum address to send the transaction from.
            *args: Arguments required by the function.

        Returns:
            The transaction receipt object.
        """
        
        try:
            max_attempts = 3
            private_key = None

            for _ in range(max_attempts):
                input_key = getpass.getpass('Insert private key to confirm the transaction: ').strip()

                if re.fullmatch(r'0x[a-fA-F0-9]{64}', input_key):
                    private_key = input_key
                    break
                else:
                    print(f"{Fore.YELLOW}Invalid private key format. Please try again.{Style.RESET_ALL}")
            
            if private_key is None:
                print(f"{Fore.RED}Too many invalid attempts. Transaction aborted.{Style.RESET_ALL}")
                return FailedReceipt(status=0)

            account = self.w3.eth.account.from_key(private_key)

            if account.address.lower() != from_address.lower():
                print(f"{Fore.RED}That private key doesn't match your account. Transaction cancelled.{Style.RESET_ALL}")
                return FailedReceipt(status=0)
        
            function = getattr(self.contract.functions, function_name)(*args)
            gas_estimate = function.estimate_gas({'from': from_address})
           
            transaction = function.build_transaction({
            'from': from_address,
            'nonce': self.w3.eth.get_transaction_count(from_address),
            'gas': int(gas_estimate),
            'gasPrice': self.w3.eth.gas_price
            })
            
            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key=private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            log_msg(f"Transaction {function_name} executed. From: {from_address}, Tx Hash: {tx_hash.hex()}, Gas: {gas_estimate}, Gas Price: {self.w3.eth.gas_price}")

            return receipt

        except Exception as e:
            log_error(f"Error executing {function_name} from {from_address}. Error: {str(e)}")
            raise e
        
    
    def add_user(self, name: str, last_name: str, user_role: str, from_address: str):
        """
        Calls addUser(name, lastName)
        """
        from_address = Web3.to_checksum_address(from_address)
        return self.write_data_user('addUser', from_address, name, last_name, user_role)
    

    def update_user(self, name: str, last_name: str, user_role: str, from_address: str):
        """
        Calls updateUser(name, lastName)
        """
        from_address = Web3.to_checksum_address(from_address)
        return self.write_data('updateUser', from_address, name, last_name, user_role)
    

    def transfer_token(self, from_address: str, to_address: str, amount: int):
        """
        Calls transferToken(to, amount)
        """
        from_address = Web3.to_checksum_address(from_address)
        to_address = Web3.to_checksum_address(to_address)
        return self.write_data('transferToken', from_address, to_address, amount)
    
    
    def register_operation(self, address: str, operationType: str, operationDescription: str, delta: int, co2emissions: int):
        """
        Calls registerOperation(address, operationType, operationDescription, co2)
        """
        address = Web3.to_checksum_address(address)
        return self.write_data('registerOperation', address, operationType, operationDescription, delta, co2emissions)
    
    
    def register_green_action(self, address: str, operationDescription: str, co2saved: int):
        """
        Calls registerOperation(address, operationType, operationDescription, co2)
        """
        address = Web3.to_checksum_address(address)
        return self.write_data('registerGreenAction', address, operationDescription, co2saved)
    
    
    def check_balance(self, address: str):
        """
        Calls checkBalance(address)
        """
        address = Web3.to_checksum_address(address)
        function = getattr(self.contract.functions, 'checkBalance')()
        return function.call({'from': address})

