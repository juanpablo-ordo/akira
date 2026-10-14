import hashlib,os,tempfile
from pathlib import Path
from execution import Blocked

class AccountLock:
    """Bloqueo del SO por cuenta/servidor, compartido con la anterior V149."""
    def __init__(self,account):
        identity=f"{account.server}:{account.login}".encode()
        name=hashlib.sha256(identity).hexdigest()[:20]
        path=Path(tempfile.gettempdir())/f"akira149_{name}.lock"
        self.stream=path.open("a+b")
        if self.stream.tell()==0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise Blocked("ya hay otra Akira operando esta cuenta; ciérrala antes de continuar")

    def close(self):
        self.stream.close()
