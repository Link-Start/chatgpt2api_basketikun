import os
import unittest

from services.register import openai_register


RUN_REGISTER_ACCOUNT_TEST = os.environ.get("RUN_REGISTER_ACCOUNT_TEST") == "1"


@unittest.skipUnless(
    RUN_REGISTER_ACCOUNT_TEST,
    "set RUN_REGISTER_ACCOUNT_TEST=1 to run one real register task",
)
class RegisterAccountTest(unittest.TestCase):
    def test_register_one_account(self):
        openai_register.stats.update({
            "done": 0,
            "success": 0,
            "fail": 0,
            "start_time": openai_register.time.time(),
        })

        result = openai_register.worker(1)

        self.assertTrue(result.get("ok"), result.get("error"))
        account = result.get("result") or {}
        self.assertTrue(account.get("email"))
        self.assertTrue(account.get("access_token"))
        self.assertTrue(account.get("refresh_token"))


if __name__ == "__main__":
    unittest.main()
