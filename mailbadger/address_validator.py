from validate_email import validate_email
from DNS.Base import TimeoutError
from multiprocessing import Pool
from functools import partial
import signal

TIMEOUT = 999999999

OBVIOUSLY_FAKE_ADDRESSES = [
    'poo.thisisfake'
    'agh12345djfj',
    'zvngh99fla',
    'bogardcaof',
    '975489qyewof9y__esr78ye4847t____',
    '1234567wgjskxSNFJBGvje5___________SSSAJWNN',
    'foofoofoofoofoofoofooBLAHBLAHBLAHhahahah2742'
]

def _validate(addr, verbose=False):
    try:
        result = validate_email(addr, verify=True)

        if verbose:
            if result:
                print '{email} exists'.format(email=addr)
            else:
                print '{email} does not exist'.format(email=addr)

        if not result:
            result = False
        return (addr, result)
    except TimeoutError as e:
        if verbose:
            print 'Timed out validating {email}'.format(email=addr)
        return (addr, False)

class AddressValidator:

    def __init__(self, num_processes):
        self._num_processes = num_processes

    def _create_pool(self):
        # Make the process ignore SIGINT before a process Pool is created. This
        # way created child processes inherit SIGINT handler.
        original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        proc_pool = Pool(self._num_processes)
        # Restore the original SIGINT handler in the parent process after a Pool
        # has been created.
        signal.signal(signal.SIGINT, original_sigint_handler)

        return proc_pool

    def _domain_has_email_server(self, domain):
        # ensure domain has a detectable SMTP server before doing anything
        return validate_email(
            'test@{domain}'.format(domain=domain), check_mx=True)

    def validate_email_server(self, domain, verbose=False):
        if not self._domain_has_email_server(domain):
            if verbose:
                msg = 'Cannot detect mail server at "{domain}"'
                print msg.format(domain=domain)
            return False

        # Some mail servers always say every email you request exists. To
        # prevent those servers misleading users, we consider the mail server
        # invalid if they say every email address from a collection of obviously
        # fake addresses exist.
        if verbose:
            print 'Ensuring mail sever does not state every email address exists'

        fakeEmails = [
            '{:s}@{:s}'.format(addr, domain) for addr in OBVIOUSLY_FAKE_ADDRESSES
        ]
        fakeEmailExistences = [
            _validate(email, verbose=verbose) for email in fakeEmails
        ]
        if all(exists[1] == True for exists in fakeEmailExistences):
            if verbose:
                msg = 'Mail server at {domain} said all fake dummy addresses'
                msg += ' exist, cannot use it for validating addresses'
                print msg.format(domain=domain)
            return False

        return True

    def validate_addresses(self, addresses, domain, verbose=False):
        if not self.validate_email_server(domain, verbose):
            return []

        # Validate the specified addresses exist on the specified domain
        addresses = [ '{:s}@{:s}'.format(addr, domain) for addr in addresses ]
        validate_func = partial(_validate, verbose=verbose)

        # Use `map_async()` so we can gracefully handle keyboard interrupts.
        # We want the interrupt to terminal *all* child processes, which won't
        # happen with the blocking `map()` call.
        #
        # TODO: handle interrupts gracefully *and* don't recreate it every call.
        pool = self._create_pool()
        interrupt_to_raise = None
        try:
            async_results = pool.map_async(validate_func, addresses)
            results = async_results.get(TIMEOUT) # need timeout for interrupt to work
        except KeyboardInterrupt as e:
            pool.terminate()
            interrupt_to_raise = e
        else:
            pool.close()
        pool.join()

        # Continue bubbling the interrupt upwards.
        if interrupt_to_raise:
            raise e

        # only return addresses which exist
        return [ res[0] for res in results if res[1] ]
