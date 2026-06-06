from rawcd.server import main, parse_args


def test_parse_server_args_defaults_to_loopback_port() -> None:
    args = parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_main_passes_app_and_bind_address_to_runner() -> None:
    calls = []

    def runner(app, host: str, port: int, log_level: str) -> None:
        calls.append((app.title, host, port, log_level))

    main(["--host", "0.0.0.0", "--port", "9000"], runner=runner)

    assert calls == [("RawCD Engine", "0.0.0.0", 9000, "info")]
