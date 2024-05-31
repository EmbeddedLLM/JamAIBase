import re


def is_valid_ipv4(ip):
    pattern = re.compile(
        r"^(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    )
    return pattern.match(ip) is not None


def is_valid_port(port):
    return 0 <= int(port) <= 65535


def expand_port_ranges(port_ranges):
    ports = []
    for part in port_ranges.split(","):
        if "-" in part:
            start, end = part.split("-")
            ports.extend(range(int(start), int(end) + 1))
        else:
            ports.append(int(part))
    return ports


def validate_and_process_ip_address(input_string):
    urls = input_string.split("|")
    result = []

    for url in urls:
        if not url:
            continue
        match = re.match(r"http://(\d+\.\d+\.\d+\.\d+):(.+)", url)
        if not match:
            return "Input is invalid"

        ip, port_ranges = match.groups()
        if not is_valid_ipv4(ip):
            return "Input is invalid"

        try:
            ports = expand_port_ranges(port_ranges)
            for port in ports:
                if not is_valid_port(port):
                    return "Input is invalid"
                result.append(f"http://{ip}:{port}")
        except ValueError:
            return "Input is invalid"

    return result


if __name__ == "__main__":

    def test_input_vllm_url():
        test_case = []

        test_case.append(
            {"input": "http://192.168.1.1:1234", "expected": ["http://192.168.1.1:1234"]}
        )

        test_case.append(
            {
                "input": "http://192.168.171.1:1234,1235,1237",
                "expected": [
                    "http://192.168.171.1:1234",
                    "http://192.168.171.1:1235",
                    "http://192.168.171.1:1237",
                ],
            }
        )

        test_case.append(
            {
                "input": "http://192.6.171.1:1234-1237",
                "expected": [
                    "http://192.6.171.1:1234",
                    "http://192.6.171.1:1235",
                    "http://192.6.171.1:1236",
                    "http://192.6.171.1:1237",
                ],
            }
        )

        test_case.append(
            {
                "input": "http://10.168.171.1:1234|http://192.168.171.1:1256",
                "expected": ["http://10.168.171.1:1234", "http://192.168.171.1:1256"],
            }
        )

        test_case.append(
            {
                "input": "http://192.168.171.6:2345|http://192.168.171.1:1234,1235,1237|",
                "expected": [
                    "http://192.168.171.6:2345",
                    "http://192.168.171.1:1234",
                    "http://192.168.171.1:1235",
                    "http://192.168.171.1:1237",
                ],
            }
        )

        test_case.append(
            {
                "input": "http://192.168.171.1:1234-1237|http://192.168.171.6:2345",
                "expected": [
                    "http://192.168.171.1:1234",
                    "http://192.168.171.1:1235",
                    "http://192.168.171.1:1236",
                    "http://192.168.171.1:1237",
                    "http://192.168.171.6:2345",
                ],
            }
        )

        test_case.append(
            {
                "input": "http://192.168.171.1:1234-1237|https://192.168.171.6:2345",
                "expected": [
                    "http://192.168.171.1:1234",
                    "http://192.168.171.1:1235",
                    "http://192.168.171.1:1236",
                    "http://192.168.171.1:1237",
                    "http://192.168.171.6:2345",
                ],
            }
        )

        return test_case

    valid_test_cases = test_input_vllm_url()

    for test_case in valid_test_cases:
        output = validate_and_process_ip_address(test_case["input"])
        assert output == test_case["expected"], f"{output} \n {test_case['expected']}"
