from pw_channel.channels.voice.telephony.base import TelephonyProvider


class WebsiteTelephony(TelephonyProvider):
    name = "website"
    supports_outbound = False
    supports_transfer = False

    def websocket_endpoint(self):
        from pw_channel.channels.voice.routes.ws import ws_website

        return ws_website
