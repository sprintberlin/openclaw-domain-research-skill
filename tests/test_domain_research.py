"""Offline unit tests for openclaw-domain-research-skill helpers."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import domain_research as dr  # noqa: E402


class TestNormalizeDomain(unittest.TestCase):
    def test_plain_domain(self):
        self.assertEqual(dr.normalize_domain("Example.COM"), "example.com")

    def test_url_and_trailing_dot(self):
        self.assertEqual(dr.normalize_domain("https://Example.com/path?q=1"), "example.com")
        self.assertEqual(dr.normalize_domain("example.com."), "example.com")

    def test_host_with_port(self):
        self.assertEqual(dr.normalize_domain("example.com:8080"), "example.com")

    def test_idn(self):
        self.assertEqual(dr.normalize_domain("münchen.de"), "xn--mnchen-3ya.de")

    def test_invalid(self):
        for bad in ("", "http://", "no-dot", "a b.com", "-bad.com", "bad-.com", "x" * 64 + ".com"):
            with self.assertRaises(dr.DomainResearchError, msg=bad):
                dr.normalize_domain(bad)

    def test_normalize_domains_csv_and_dedupe(self):
        self.assertEqual(
            dr.normalize_domains(["a.com, b.com", "a.com"]),
            ["a.com", "b.com"],
        )

    def test_normalize_tld(self):
        self.assertEqual(dr.normalize_tld(".COM"), "com")
        self.assertEqual(dr.normalize_tld("co.uk"), "co.uk")
        with self.assertRaises(dr.DomainResearchError):
            dr.normalize_tld("-bad")


class TestParsers(unittest.TestCase):
    def test_parse_bool(self):
        self.assertIs(dr.parse_bool("true"), True)
        self.assertIs(dr.parse_bool("false"), False)
        self.assertIs(dr.parse_bool(None), None)

    def test_money_or_none(self):
        self.assertEqual(dr.money_or_none("0"), None)
        self.assertEqual(dr.money_or_none("13000.0000"), "13000.0000")
        self.assertIsNone(dr.money_or_none("abc"))

    def test_none_if_zero(self):
        self.assertIsNone(dr.none_if_zero("0"))
        self.assertEqual(dr.none_if_zero("12"), "12")

    def test_extension_for(self):
        self.assertEqual(dr.extension_for("example.co.uk"), "co.uk")
        self.assertEqual(dr.extension_for("example.com"), "com")
        self.assertEqual(dr.extension_for("a.b.example.com"), "com")


class TestCheckParsing(unittest.TestCase):
    XML = """<?xml version="1.0"?>
    <ApiResponse xmlns="http://api.namecheap.com/xml.response" Status="OK">
      <Errors/>
      <CommandResponse Type="namecheap.domains.check">
        <DomainCheckResult Domain="Free.COM" Available="true" ErrorNo="0"
          IsPremiumName="false" PremiumRegistrationPrice="0" IcannFee="0.0000" EapFee="0.0"/>
        <DomainCheckResult Domain="Taken.com" Available="false" ErrorNo="0"
          IsPremiumName="true" PremiumRegistrationPrice="13000.0000" PremiumRenewalPrice="13000.0000" IcannFee="0.20"/>
      </CommandResponse>
    </ApiResponse>"""

    def test_client_check(self):
        client = dr.NamecheapClient(dr.NamecheapConfig("u", "k", "u", "127.0.0.1"))
        original = client.call
        client.call = lambda command, **params: dr.ET.fromstring(self.XML)
        rows = client.check(["free.com", "taken.com"])
        self.assertTrue(rows[0]["available"])
        self.assertFalse(rows[0]["premium"])
        self.assertFalse(rows[1]["available"])
        self.assertTrue(rows[1]["premium"])
        self.assertEqual(rows[1]["premium_registration_price"], "13000.0000")
        self.assertEqual(rows[1]["icann_fee"], "0.20")


class TestPricingParsing(unittest.TestCase):
    XML = """<?xml version="1.0"?>
    <ApiResponse xmlns="http://api.namecheap.com/xml.response" Status="OK">
      <Errors/>
      <CommandResponse Type="namecheap.users.getPricing">
        <UserGetPricingResult>
          <ProductType Name="domains"/>
          <ProductCategory Name="register"/>
          <Product Name="com">
            <Price Duration="1" DurationType="YEAR" Price="11.28" AdditionalCost="0.20"
              Currency="USD" RegularPrice="14.98" YourPrice="11.28" PromotionPrice="0.0" PricingType="ABSOLUTE"/>
            <Price Duration="2" DurationType="YEAR" Price="11.48" AdditionalCost="0.20"
              Currency="USD" PricingType="MULTIPLE"/>
          </Product>
        </UserGetPricingResult>
      </CommandResponse>
    </ApiResponse>"""

    def test_client_pricing(self):
        client = dr.NamecheapClient(dr.NamecheapConfig("u", "k", "u", "127.0.0.1"))
        client.call = lambda command, **params: dr.ET.fromstring(self.XML)
        row = client.pricing("com", "REGISTER", 1)
        self.assertEqual(row["price"], "11.28")
        self.assertEqual(row["total"], "11.48")
        self.assertEqual(row["currency"], "USD")
        with self.assertRaises(dr.NamecheapError):
            client.pricing("net", "REGISTER", 1)


class TestErrors(unittest.TestCase):
    ERROR_XML = """<?xml version="1.0"?>
    <ApiResponse xmlns="http://api.namecheap.com/xml.response" Status="ERROR">
      <Errors>
        <Error Number="1011101">IP not allowed</Error>
      </Errors>
    </ApiResponse>"""

    def test_error_raised(self):
        with self.assertRaises(dr.NamecheapError) as ctx:
            dr.parse_namecheap_response(self.ERROR_XML)
        self.assertIn("IP not allowed", str(ctx.exception))

    def test_invalid_xml(self):
        with self.assertRaises(dr.NamecheapError):
            dr.parse_namecheap_response("<not-xml")


class TestExpandBareNames(unittest.TestCase):
    def test_expand_bare_name(self):
        domains = dr.expand_bare_names(["mybrand"], ["com", "de", "ai"])
        self.assertEqual(domains, ["mybrand.com", "mybrand.de", "mybrand.ai"])

    def test_normalize_bare_names(self):
        names = dr.normalize_bare_names(["MyBrand", "other-brand"])
        self.assertEqual(names, ["mybrand", "other-brand"])
        with self.assertRaises(dr.DomainResearchError):
            dr.normalize_bare_name("bad.com")

    def test_parse_tld_list(self):
        tlds = dr.parse_tld_list("com, .de, AI, com")
        self.assertEqual(tlds, ["com", "de", "ai"])


class TestCli(unittest.TestCase):
    def test_unknown_command_exits_two(self):
        with self.assertRaises(SystemExit) as ctx:
            dr.main(["nope"])
        self.assertEqual(ctx.exception.code, 2)

    def test_check_requires_domain(self):
        with self.assertRaises(SystemExit) as ctx:
            dr.main(["check"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
