import io
import json
import unittest
import zipfile

from generator import build_zip, discord_files, fivem_files, site_files, custom_files


ORDER = {"id": "BF-TEST-0001"}


class GeneratorSmokeTests(unittest.TestCase):
    def assert_zip_valid(self, files):
        self.assertTrue(files)
        for name, content in files.items():
            self.assertTrue(name)
            self.assertIsInstance(content, str)
        archive = build_zip(files)
        self.assertGreater(len(archive), 100)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            self.assertEqual(set(z.namelist()), set(files.keys()))
            self.assertTrue(z.testzip() is None)

    def test_discord_generation(self):
        config = {
            "objective": "Bot para meu servidor",
            "bot_name": "Forge Test",
            "moderation": ["Ban", "Kick", "Mute"],
            "tickets": ["Criar ticket", "Fechamento automático"],
            "economy": ["Saldo", "Loja", "Ranking"],
            "automation": ["AutoRole", "Verificação", "Boas-vindas"],
            "logs": ["Entradas/Saídas", "Auditoria"],
            "ui": ["Embeds", "Botões"],
            "integrations": ["Webhooks"],
        }
        files = discord_files(ORDER, config)
        self.assertIn("src/index.js", files)
        self.assertIn("config/features.json", files)
        self.assertIn("DISCORD_TOKEN=", files[".env.example"])
        self.assertIn("ban", files["src/index.js"])
        self.assertIn("ticket", files["src/index.js"])
        self.assertNotIn("DISCORD_TOKEN=", files["src/index.js"])
        self.assert_zip_valid(files)

    def test_fivem_generation(self):
        config = {
            "objective": "Sistema de emprego",
            "framework": "QBCore",
            "system_type": "Emprego",
            "nui": ["Menu", "Notificações"],
            "database": "MySQL",
            "jobs": "Polícia, EMS",
            "discord_logs": ["Logs"],
        }
        files = fivem_files(ORDER, config)
        self.assertIn("fxmanifest.lua", files)
        self.assertIn("QBCore", files["client.lua"])
        self.assertIn("web/index.html", files)
        self.assertIn("README-DATABASE.md", files)
        self.assertIn("Config =", files["config.lua"])
        self.assert_zip_valid(files)

    def test_site_generation(self):
        config = {
            "objective": "Site de vendas",
            "brand": "Forge Store",
            "pages": "Início, Produtos, Contato",
            "sections": "Hero, Preços, FAQ",
            "forms": ["Contato"],
            "seo": "Incluir",
        }
        files = site_files(ORDER, config)
        self.assertIn("index.html", files)
        self.assertIn("style.css", files)
        self.assertIn("app.js", files)
        self.assertIn("Forge Store", files["index.html"])
        self.assertIn('name="description"', files["index.html"])
        self.assert_zip_valid(files)

    def test_custom_generation(self):
        config = {
            "objective": "Sistema sob medida",
            "platform": "Web / Site",
            "features": "Login, painel, relatórios",
            "integrations": "Discord API",
        }
        files = custom_files(ORDER, config)
        self.assertIn("README.md", files)
        self.assertIn("project-spec.json", files)
        spec = json.loads(files["project-spec.json"])
        self.assertEqual(spec["platform"], "Web / Site")
        self.assert_zip_valid(files)


if __name__ == "__main__":
    unittest.main(verbosity=2)
