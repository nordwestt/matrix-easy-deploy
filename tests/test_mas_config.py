import os
import unittest
from unittest.mock import patch

from scripts import mas_config


class MasConfigSigningKeyTests(unittest.TestCase):
    def test_normalize_pem_private_key_strips_ec_parameters(self):
        combined = "\n".join(
            [
                "-----BEGIN EC PARAMETERS-----",
                "BggqhkjOPQMBBw==",
                "-----END EC PARAMETERS-----",
                "-----BEGIN EC PRIVATE KEY-----",
                "MHcCAQEEICBFPwH0N1wGI83vE2z91UweR/0p8TyEXCkhhqn76CfXoAoGCCqGSM49",
                "-----END EC PRIVATE KEY-----",
            ]
        )
        normalized = mas_config._normalize_pem_private_key(combined)
        self.assertNotIn("EC PARAMETERS", normalized)
        self.assertIn("BEGIN EC PRIVATE KEY", normalized)

    def test_mas_signing_keys_usable_rejects_stub(self):
        stub = mas_config._generate_mas_signing_material_stub()["MAS_SIGNING_KEYS"]
        self.assertFalse(mas_config._mas_signing_keys_usable(stub))

    def test_mas_signing_keys_usable_accepts_openssl_rsa(self):
        material = mas_config._generate_mas_signing_material_openssl()
        self.assertTrue(mas_config._mas_signing_keys_usable(material["MAS_SIGNING_KEYS"]))
        key = material["MAS_SIGNING_KEYS"][0]["key"]
        self.assertIn("BEGIN PRIVATE KEY", key)
        self.assertNotIn("EC PARAMETERS", key)

    def test_build_mas_signing_keys_yaml_uses_literal_block(self):
        material = mas_config._generate_mas_signing_material_openssl()
        yaml_text = mas_config.build_mas_signing_keys_yaml_from_state(
            {
                "MAS_ENCRYPTION_SECRET": material["MAS_ENCRYPTION_SECRET"],
                "MAS_SIGNING_KEYS": material["MAS_SIGNING_KEYS"],
            }
        )
        self.assertIn("secrets:", yaml_text)
        self.assertIn("key: |", yaml_text)
        self.assertIn("BEGIN PRIVATE KEY", yaml_text)
        self.assertNotIn("EC PARAMETERS", yaml_text)

    def test_ensure_mas_secrets_regenerates_invalid_keys(self):
        invalid = mas_config._generate_mas_signing_material_stub()
        state = {
            "MAS_DB_PASSWORD": "db",
            "MAS_HOMESERVER_SECRET": "hs",
            "MAS_SYNAPSE_CLIENT_SECRET": "client",
            "MAS_ENCRYPTION_SECRET": invalid["MAS_ENCRYPTION_SECRET"],
            "MAS_SIGNING_KEYS": invalid["MAS_SIGNING_KEYS"],
        }
        with patch.dict(os.environ, {"MED_ALLOW_INSECURE_MAS_KEYS": "0"}, clear=False):
            updated = mas_config.ensure_mas_secrets(state, mas_enabled=True)
        self.assertTrue(mas_config._mas_signing_keys_usable(updated["MAS_SIGNING_KEYS"]))
        self.assertNotEqual(updated["MAS_SIGNING_KEYS"], invalid["MAS_SIGNING_KEYS"])


class MasConfigUpstreamOauth2Tests(unittest.TestCase):
    def test_stable_provider_ulid_is_deterministic(self):
        first = mas_config.stable_provider_ulid("Google", "https://accounts.google.com/")
        second = mas_config.stable_provider_ulid("Google", "https://accounts.google.com/")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 26)

    def test_ensure_sso_provider_ids_assigns_and_preserves(self):
        config = {
            "features": {
                "sso": {
                    "enabled": True,
                    "providers": [
                        {
                            "name": "Google",
                            "issuer": "https://accounts.google.com/",
                            "client_id": "id",
                            "client_secret": "secret",
                        },
                        {
                            "id": "01AAAAAAAAAAAAAAAAAAAAAAAA",
                            "name": "Microsoft",
                            "issuer": "https://login.microsoftonline.com/common/v2.0",
                            "client_id": "id2",
                            "client_secret": "secret2",
                        },
                    ],
                }
            }
        }
        self.assertTrue(mas_config.ensure_sso_provider_ids(config))
        google_id = config["features"]["sso"]["providers"][0]["id"]
        self.assertEqual(len(google_id), 26)
        self.assertEqual(
            config["features"]["sso"]["providers"][1]["id"],
            "01AAAAAAAAAAAAAAAAAAAAAAAA",
        )
        self.assertFalse(mas_config.ensure_sso_provider_ids(config))

    def test_mas_upstream_redirect_uri(self):
        uri = mas_config.mas_upstream_redirect_uri(
            "https://matrix.example.com/auth/",
            "01HFVBY12TMNTYTBV8W921M5FA",
        )
        self.assertEqual(
            uri,
            "https://matrix.example.com/auth/upstream/callback/01HFVBY12TMNTYTBV8W921M5FA",
        )

    def test_matrix_kanidm_redirect_uri_matches_mas_public_base(self):
        uri = mas_config.matrix_kanidm_redirect_uri("matrix.test.example", "idm.test.example")
        provider_id = mas_config.matrix_kanidm_provider_id("idm.test.example")
        self.assertEqual(len(provider_id), 26)
        self.assertEqual(
            uri,
            f"https://matrix.test.example/auth/upstream/callback/{provider_id}",
        )
        self.assertEqual(
            mas_config.matrix_kanidm_provider_id("idm.test.example"),
            mas_config.stable_provider_ulid(
                "Kanidm", "https://idm.test.example/oauth2/openid/matrix"
            ),
        )

    def test_build_kanidm_matrix_client_uses_element_host_for_app_tile(self):
        same_host = mas_config.build_kanidm_matrix_client(
            matrix_domain="matrix.example.com",
            kanidm_domain="idm.example.com",
            client_id="matrix",
            element_domain="matrix.example.com",
        )
        self.assertEqual(same_host["landing_url"], "https://matrix.example.com")
        self.assertEqual(same_host["image"], "https://matrix.example.com/vector-icons/144.png")

        split = mas_config.build_kanidm_matrix_client(
            matrix_domain="matrix.example.com",
            kanidm_domain="idm.example.com",
            client_id="matrix",
            element_domain="chat.example.com",
        )
        self.assertEqual(split["landing_url"], "https://chat.example.com")
        self.assertEqual(split["image"], "https://chat.example.com/vector-icons/144.png")
        self.assertTrue(split["redirect_uris"][0].startswith("https://matrix.example.com/auth/"))

        no_element = mas_config.build_kanidm_matrix_client(
            matrix_domain="matrix.example.com",
            kanidm_domain="idm.example.com",
            client_id="matrix",
        )
        self.assertEqual(no_element["landing_url"], "https://matrix.example.com")
        self.assertNotIn("image", no_element)

    def test_resolve_sso_default_login_kanidm_vs_chooser(self):
        kanidm = {
            "features": {
                "sso": {
                    "enabled": True,
                    "provider": "kanidm",
                    "providers": [
                        {
                            "name": "Kanidm",
                            "issuer": "https://idm.test.example/oauth2/openid/matrix",
                            "client_id": "matrix",
                        }
                    ],
                }
            }
        }
        google = {
            "features": {
                "sso": {
                    "enabled": True,
                    "providers": [
                        {
                            "name": "Google",
                            "issuer": "https://accounts.google.com/",
                            "client_id": "g",
                        }
                    ],
                }
            }
        }
        self.assertEqual(mas_config.resolve_sso_default_login(kanidm), "sso")
        self.assertEqual(mas_config.resolve_sso_default_login(google), "chooser")
        kanidm["features"]["sso"]["default_login"] = "chooser"
        self.assertEqual(mas_config.resolve_sso_default_login(kanidm), "chooser")

    def test_build_mas_upstream_oauth2_yaml_uses_string_scope(self):
        providers = [
            {
                "id": "01HFVBY12TMNTYTBV8W921M5FA",
                "name": "Google",
                "issuer": "https://accounts.google.com/",
                "client_id": "id",
                "client_secret": "secret",
            }
        ]
        yaml_text = mas_config.build_mas_upstream_oauth2_yaml(
            providers,
            "https://matrix.example.com/auth/",
        )
        self.assertIn('scope: openid profile email', yaml_text)
        self.assertNotIn("- openid\n", yaml_text)
        self.assertIn(
            "redirect_uri: https://matrix.example.com/auth/upstream/callback/01HFVBY12TMNTYTBV8W921M5FA",
            yaml_text,
        )
        self.assertIn("localpart:\n        action: ignore", yaml_text)
        self.assertNotIn("preferred_username", yaml_text)
        self.assertIn("account_name:\n        template: '{{ user.email }}'", yaml_text)
        self.assertNotIn("id_token_signed_response_alg", yaml_text)

    def test_build_mas_upstream_oauth2_yaml_kanidm_uses_es256(self):
        providers = [
            {
                "id": "01HFVBY12TMNTYTBV8W921M5FA",
                "name": "Kanidm",
                "issuer": "https://idm.test.example/oauth2/openid/matrix",
                "client_id": "matrix",
                "client_secret": "secret",
            }
        ]
        yaml_text = mas_config.build_mas_upstream_oauth2_yaml(
            providers,
            "https://matrix.test.example/auth/",
        )
        self.assertIn("id_token_signed_response_alg: ES256", yaml_text)

    def test_oauth_scope_string_accepts_list_or_string(self):
        self.assertEqual(
            mas_config._oauth_scope_string(["openid", "profile", "email"]),
            "openid profile email",
        )
        self.assertEqual(
            mas_config._oauth_scope_string("openid email"),
            "openid email",
        )


class MasConfigCaddyTests(unittest.TestCase):
    def test_caddy_mas_block_routes_oidc_discovery(self):
        block = mas_config.caddy_mas_block()
        self.assertIn("handle /.well-known/openid-configuration", block)
        self.assertIn("handle_path /auth/*", block)
        self.assertIn("reverse_proxy matrix_mas:8080", block)

    def test_build_caddy_element_routing_unified_host(self):
        routing = mas_config.build_caddy_element_routing(
            matrix_domain="example.com",
            server_name="example.com",
            element_enabled=True,
            element_domain="example.com",
        )
        self.assertIn("reverse_proxy matrix_element:80", routing["CADDY_ELEMENT_MATRIX_FALLBACK"])
        self.assertIn("handle /config.json", routing["CADDY_ELEMENT_MATRIX_FALLBACK"])
        self.assertEqual(routing["CADDY_ELEMENT_SITE_BLOCK"], "")

    def test_build_caddy_element_routing_separate_host(self):
        routing = mas_config.build_caddy_element_routing(
            matrix_domain="matrix.example.com",
            server_name="example.com",
            element_enabled=True,
            element_domain="element.example.com",
        )
        self.assertEqual(routing["CADDY_ELEMENT_MATRIX_FALLBACK"], "")
        self.assertIn("element.example.com {", routing["CADDY_ELEMENT_SITE_BLOCK"])
        self.assertIn("handle /config.json", routing["CADDY_ELEMENT_SITE_BLOCK"])
        self.assertNotIn("matrix_mas", routing["CADDY_ELEMENT_SITE_BLOCK"])

    def test_build_caddy_element_routing_allows_webmail_frame_ancestors(self):
        routing = mas_config.build_caddy_element_routing(
            matrix_domain="matrix.example.com",
            server_name="example.com",
            element_enabled=True,
            element_domain="chat.example.com",
            frame_ancestors=["https://webmail.test.example"],
        )
        site = routing["CADDY_ELEMENT_SITE_BLOCK"]
        self.assertIn("chat.example.com {", site)
        self.assertIn("header_down -Content-Security-Policy", site)
        self.assertIn("header_down -X-Frame-Options", site)
        self.assertIn(
            'Content-Security-Policy "frame-ancestors \'self\' https://webmail.test.example"',
            site,
        )
        self.assertNotIn("X-Frame-Options SAMEORIGIN", site)

    def test_build_caddy_element_routing_unified_host_strips_element_csp(self):
        routing = mas_config.build_caddy_element_routing(
            matrix_domain="matrix.example.com",
            server_name="example.com",
            element_enabled=True,
            element_domain="matrix.example.com",
            frame_ancestors=["webmail.test.example"],
        )
        fallback = routing["CADDY_ELEMENT_MATRIX_FALLBACK"]
        self.assertIn("header_down -Content-Security-Policy", fallback)
        self.assertIn("https://webmail.test.example", fallback)
