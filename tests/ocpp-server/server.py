import asyncio
import logging
from datetime import datetime, timezone
from threading import Timer

import ocpp.v201
import websockets
from ocpp.routing import on
from ocpp.v201.enums import (
    Action,
    AuthorizationStatusType,
    ClearCacheStatusType,
    RegistrationStatusType,
    TransactionEventType,
)
from websockets import ConnectionClosed

# Setting up the logging configuration to display debug level messages.
logging.basicConfig(level=logging.DEBUG)

ChargePoints = set()


class RepeatTimer(Timer):
    """Class that inherits from the Timer class. It will run a
    function at regular intervals."""

    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


# Define a ChargePoint class inheriting from the OCPP 2.0.1 ChargePoint class.
class ChargePoint(ocpp.v201.ChargePoint):
    # Message handlers to receive OCPP messages.
    @on(Action.BootNotification)
    async def on_boot_notification(self, charging_station, reason, **kwargs):
        logging.info("Received %s", Action.BootNotification)
        # Create and return a BootNotification response with the current time,
        # an interval of 60 seconds, and an accepted status.
        return ocpp.v201.call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=60,
            status=RegistrationStatusType.accepted,
        )

    @on(Action.Heartbeat)
    async def on_heartbeat(self, **kwargs):
        logging.info("Received %s", Action.Heartbeat)
        return ocpp.v201.call_result.Heartbeat(
            current_time=datetime.now(timezone.utc).isoformat()
        )

    @on(Action.StatusNotification)
    async def on_status_notification(
        self, timestamp, evse_id: int, connector_id: int, connector_status, **kwargs
    ):
        logging.info("Received %s", Action.StatusNotification)
        return ocpp.v201.call_result.StatusNotification()

    @on(Action.Authorize)
    async def on_authorize(self, id_token, **kwargs):
        logging.info("Received %s", Action.Authorize)
        return ocpp.v201.call_result.Authorize(
            id_token_info={"status": AuthorizationStatusType.accepted}
        )

    @on(Action.TransactionEvent)
    async def on_transaction_event(
        self,
        event_type: TransactionEventType,
        timestamp,
        trigger_reason,
        seq_no: int,
        transaction_info,
        **kwargs,
    ):
        match event_type:
            case TransactionEventType.started:
                logging.info("Received %s Started", Action.TransactionEvent)
                return ocpp.v201.call_result.TransactionEvent(
                    id_token_info={"status": AuthorizationStatusType.accepted}
                )
            case TransactionEventType.updated:
                logging.info("Received %s Updated", Action.TransactionEvent)
                return ocpp.v201.call_result.TransactionEvent(total_cost=10)
            case TransactionEventType.ended:
                logging.info("Received %s Ended", Action.TransactionEvent)
                return ocpp.v201.call_result.TransactionEvent()

    @on(Action.MeterValues)
    async def on_meter_values(self, evse_id: int, meter_value, **kwargs):
        logging.info("Received %s", Action.MeterValues)
        return ocpp.v201.call_result.MeterValues()

    # Request handlers to emit OCPP messages.
    async def send_clear_cache(self):
        request = ocpp.v201.call.ClearCache()
        response = await self.call(request)

        if response.status == ClearCacheStatusType.accepted:
            logging.info("%s successful", Action.ClearCache)
        else:
            logging.info("%s failed", Action.ClearCache)


# Function to handle new WebSocket connections.
async def on_connect(websocket, path):
    """For every new charge point that connects, create a ChargePoint instance and start
    listening for messages."""
    try:
        requested_protocols = websocket.request_headers["Sec-WebSocket-Protocol"]
    except KeyError:
        logging.info("Client hasn't requested any Subprotocol. Closing Connection")
        return await websocket.close()

    if websocket.subprotocol:
        logging.info("Protocols Matched: %s", websocket.subprotocol)
    else:
        logging.warning(
            "Protocols Mismatched | Expected Subprotocols: %s,"
            " but client supports %s | Closing connection",
            websocket.available_subprotocols,
            requested_protocols,
        )
        return await websocket.close()

    charge_point_id = path.strip("/")
    cp = ChargePoint(charge_point_id, websocket)
    ChargePoints.add(cp)
    try:
        await cp.start()
    except ConnectionClosed:
        logging.info("ChargePoint %s closed connection", cp.id)
        ChargePoints.remove(cp)
        logging.debug("Connected ChargePoint(s): %d", len(ChargePoints))


# Main function to start the WebSocket server.
async def main():
    # Create the WebSocket server and specify the handler for new connections.
    server = await websockets.serve(
        on_connect,
        "127.0.0.1",  # Listen on loopback.
        9000,  # Port number.
        subprotocols=["ocpp2.0", "ocpp2.0.1"],  # Specify OCPP 2.0.1 subprotocols.
    )
    logging.info("WebSocket Server Started")
    # Wait for the server to close (runs indefinitely).
    await server.wait_closed()


# Entry point of the script.
if __name__ == "__main__":
    # Run the main function to start the server.
    asyncio.run(main())
