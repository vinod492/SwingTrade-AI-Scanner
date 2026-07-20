class TestBacktestApi:
    async def test_create_runs_inline_without_redis(self, auth_client):
        r = await auth_client.post("/backtests", json={
            "name": "Score>80 momo",
            "params": {"min_swing_score": 80, "min_rel_volume": 2,
                       "price_above_ema": 50, "stop_loss_pct": 8,
                       "take_profit_pct": 15},
        })
        assert r.status_code == 201, r.text
        body = r.json()
        # Redis is off in tests → runs inline and completes immediately
        assert body["status"] == "done"
        assert "total_trades" in body["results"]

        r = await auth_client.get(f"/backtests/{body['id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Score>80 momo"

    async def test_list_backtests(self, auth_client):
        await auth_client.post("/backtests", json={"name": "bt1", "params": {}})
        r = await auth_client.get("/backtests")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    async def test_requires_auth(self, client):
        assert (await client.post("/backtests", json={"name": "x", "params": {}})).status_code == 401

    async def test_foreign_backtest_hidden(self, auth_client, client):
        r = await auth_client.post("/backtests", json={"name": "mine", "params": {}})
        bt_id = r.json()["id"]
        # a different user must not see it
        other = await client.post("/auth/register", json={
            "email": "other-user@example.com", "password": "supersecret1"})
        token = other.json()["access_token"]
        r = await client.get(f"/backtests/{bt_id}",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404
