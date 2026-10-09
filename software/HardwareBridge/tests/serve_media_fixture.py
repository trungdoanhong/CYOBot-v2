"""Browser acceptance fixture: in-memory SD, fake robot, never real hardware."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from test_media import CardServer
from test_studio import FakeFleet
from studio import Studio,create_server
import media

if __name__=='__main__':
    card=CardServer();media.FILE_PORT=card.port
    fleet=FakeFleet();fleet.robot.flags|=512|128
    studio=Studio(fleet_factory=lambda:fleet,auto_scan=False,connection_log_path=None)
    studio.action(dict(action='found',robots=[fleet.robot]))
    server=create_server(studio,8766)
    print('TEST ONLY: simulated SD / fake robot at http://127.0.0.1:8766',flush=True)
    try:server.serve_forever()
    finally:server.server_close();studio.close();card.close()
