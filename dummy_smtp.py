# A local fake SMTP server (accepts any login) so we can test the send flow
# without hitting real Gmail. Run separately from the real app.
import asyncio
from aiosmtpd.controller import Controller

class Handler:
    async def handle_DATA(self, server, session, envelope):
        print(f"[dummy-smtp] mail from {envelope.mail_from} to {envelope.rcpt_tos}, {len(envelope.content)} bytes")
        return '250 Message accepted for delivery'
    async def handle_AUTH(self, *a, **k):
        return '235 Authentication successful'

from aiosmtpd.smtp import AuthResult, LoginPassword

def authenticator(server, session, envelope, mechanism, auth_data):
    # Accept any credentials -- this is a local test double, not real auth.
    if isinstance(auth_data, LoginPassword):
        return AuthResult(success=True)
    return AuthResult(success=True, handled=False)

controller = Controller(
    Handler(), hostname='127.0.0.1', port=1025,
    auth_required=True, auth_require_tls=False, authenticator=authenticator,
    auth_exclude_mechanism=['NTLM'],
)
controller.start()
print("Dummy SMTP running on 127.0.0.1:1025")
import time
while True:
    time.sleep(1)
