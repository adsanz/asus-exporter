import requests, base64, datetime, json, time, os
from user_agent import generate_user_agent
from prometheus_client import start_http_server, Gauge
import logging

logging.basicConfig(level=logging.INFO)


class GeneralMetric:
    """
    Representation of Prometheus metrics and loop to fetch and transform
    application metrics into Prometheus metrics.
    """

    def __init__(self):
        """
        Initialize labels for metrics
        """
        self.router_url = os.getenv("ROUTER_URL", "www.asusrouter.com") 
        self.port = int(os.getenv("ROUTER_PORT", 8443))
        self.user = os.getenv("ROUTER_USER", "admin")
        self.password = os.getenv("ROUTER_PASSWORD", "admin")
        self.user_agent = generate_user_agent(os=('mac', 'linux'))

    
    def login(self):
        """
        Login to router and get cookie
        """
        # encode user and pass
        user_pass = f"{self.user}:{self.password}"
        user_pass_encoded = base64.b64encode(user_pass.encode("utf-8"))
        session = requests.Session()
        login_req = session.post(
            f"https://{self.router_url}:{self.port}/login.cgi",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": f"https://{self.router_url}:{self.port}",
                "Connection": "keep-alive",
                "Referer": f"https://{self.router_url}:{self.port}/Main_Login.asp",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
            },
            data={
                "group_id": "",
                "action_mode": "",
                "action_script": "",
                "action_wait": "5",
                "current_page": "Main_Login.asp",
                "next_page": "index.asp",
                "login_authorization": user_pass_encoded,
                "login_captcha": "",
            },
            verify=False,
        )
        # set cookie asus_s_token from login req as a header for stats_req
        cookie = login_req.cookies.get("asus_s_token")
        return {"cookie": cookie, "session": session}

    def fetch_clients(self, session, cookie):
        stats_req = session.get(
            f"https://{self.router_url}:{self.port}/appGet.cgi?hook=get_clientlist()",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "X-Requested-With": "XMLHttpRequest",
                "Connection": "keep-alive",
                "Referer": f"https://{self.router_url}:{self.port}/index.asp",
                "Cookie": f"asus_s_token={cookie}; clickedItem_tab=0; bw_rtab=INTERNET; ASUS_TrafficMonitor_unit=1; bw_24tab=INTERNET; bw_24refresh=1; maxBandwidth=100",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            verify=False,
        )
        return stats_req.json()["get_clientlist"]



class GeneralTrafficBySource(GeneralMetric):
    """
    Gather general traffic by source (load / download)

    """
    def __init__(self):
        self.labels = ["source"]
        self.general_load_traffic = Gauge(
            "general_load_traffic",
            "General load traffic",
            self.labels,
        )
        self.general_download_traffic = Gauge(
            "general_download_traffic",
            "General download traffic",
            self.labels,
        )
        super().__init__()

    def fetch(self):
        session = self.login()
        cookie = session["cookie"]
        current_epoch_time = int(datetime.datetime.now().timestamp())
        current_epoch_plus_1h = int(current_epoch_time + 3600)
        stats_wan_general_req = session["session"].get(
            f"https://{self.router_url}:{self.port}/getWanTraffic.asp?client=all&mode=detail&dura=24&date={current_epoch_time}&_={current_epoch_plus_1h}",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "X-Requested-With": "XMLHttpRequest",
                "Connection": "keep-alive",
                "Referer": f"https://{self.router_url}:{self.port}/index.asp",
                "Cookie": f"asus_s_token={cookie}; clickedItem_tab=0; bw_rtab=INTERNET; ASUS_TrafficMonitor_unit=1; bw_24tab=INTERNET; bw_24refresh=1; maxBandwidth=100",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            verify=False,
        )
        text_raw = stats_wan_general_req.text.split('= ')[-1].split(';')[0]
        json_text = json.loads(text_raw)
        for data in json_text:
            self.general_load_traffic.labels(data[0]).set(data[1])
            self.general_download_traffic.labels(data[0]).set(data[2])
        session["session"].close()


class TrafficPerClient(GeneralMetric):
    """
    Gather traffic per connected client (load / download)

    """
    def __init__(self):
        self.labels = ["source", "client", "client_ip", "client_vendor", "client_name"]
        self.client_load_traffic = Gauge(
            "client_load_traffic",
            "Client load traffic",
            self.labels,
        )
        self.client_download_traffic = Gauge(
            "client_download_traffic",
            "Client download traffic",
            self.labels,
        )
        super().__init__()
            

    def fetch(self):
        session = self.login()
        cookie = session["cookie"]
        current_epoch_time = int(datetime.datetime.now().timestamp())
        current_epoch_plus_1h = int(current_epoch_time + 3600)
        clients = self.fetch_clients(session["session"], cookie)
        for mac,details in clients.items():
            stats_wan_general_req = session["session"].get(
                f"https://{self.router_url}:{self.port}/getWanTraffic.asp?client={mac}&mode=detail&dura=24&date={current_epoch_time}&_={current_epoch_plus_1h}",
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "X-Requested-With": "XMLHttpRequest",
                    "Connection": "keep-alive",
                    "Referer": f"https://{self.router_url}:{self.port}/index.asp",
                    "Cookie": f"asus_s_token={cookie}; clickedItem_tab=0; bw_rtab=INTERNET; ASUS_TrafficMonitor_unit=1; bw_24tab=INTERNET; bw_24refresh=1; maxBandwidth=100",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                },
                verify=False,
            )
            text_raw = stats_wan_general_req.text.split('= ')[-1].split(';')[0]
            json_text = json.loads(text_raw)
            for data in json_text:
                self.client_load_traffic.labels(data[0], details["name"], details["ip"], details["vendor"], details["mac"]).set(data[1])
                self.client_download_traffic.labels(data[0], details["name"], details["ip"], details["vendor"], details["mac"]).set(data[2])
        session["session"].close()

class MetricManager:
    def __init__(self):
        self.general_traffic_by_source = GeneralTrafficBySource()
        self.general_traffic_by_client = TrafficPerClient()


    def run_metrics_loop(self):
        """Metrics fetching loop"""
        # suppress https warnings
        requests.packages.urllib3.disable_warnings()
        while True:
            logging.info("Fetching metrics")
            logging.info("Fetching general traffic by source")
            self.general_traffic_by_source.fetch()
            logging.info("Fetching general traffic by client")
            self.general_traffic_by_client.fetch()
            time.sleep(30)


def main():
    """Main entry point"""
    exporter_port = 9877

    metric_manager = MetricManager()
    start_http_server(exporter_port)
    metric_manager.run_metrics_loop()

if __name__ == "__main__":
    main()