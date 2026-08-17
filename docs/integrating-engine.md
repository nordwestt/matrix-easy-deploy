# Integrating with Easy Deploy Engine

For a **multi-service VPS**, use `proxy.mode: integrate` so this kit does not bind :443.

```yaml
proxy:
  type: caddy
  mode: integrate
  integrate:
    network: easydeploy-net
```

Then run `bash wizard.sh` in [easydeploy-engine](https://github.com/opencomp-eu/easydeploy-engine) (it can clone this repo as a sibling if needed), or apply this kit, then the engine, by hand. The engine wizard sets `proxy.mode: integrate` and starts shared Caddy.

Manual equivalent:

1. `bash apply.sh` here — writes `.matrix-easy-deploy/integration/caddy.caddy` and skips the local `caddy` container
2. `bash apply.sh` in easydeploy-engine with Matrix enabled in `engine.yaml`

Public backends join `easydeploy-net` so `easydeploy_caddy` can reach Synapse, Element, MAS, LiveKit JWT, and optional modules. The internal `caddy_net` mesh is kept for guest federation aliases.

LiveKit still uses host networking; engine Caddy reaches it via `host.docker.internal:7880`.

Standalone mode (`mode: standalone`, default) keeps the local `caddy` container on ports 80/443.

SSO stays **MAS** with optional upstream OIDC providers (Google, Entra, …). Authelia as a Matrix IdP is not wired by the engine yet.

See [easydeploy-engine/docs/integrated-vps.md](https://github.com/opencomp-eu/easydeploy-engine/blob/master/docs/integrated-vps.md).
