"""Tests para _pick_preflight_phrase y el sistema de preflight acción+dominio.

Sin Ollama ni proceso externo.
"""
import re
import unittest


def _import():
    from agent.loop import _pick_preflight_phrase, _PF_ACTIONS, _PF_DOMAINS, _PF_PHRASES
    return _pick_preflight_phrase, _PF_ACTIONS, _PF_DOMAINS, _PF_PHRASES


class TestPickPreflightPhrase(unittest.TestCase):

    def setUp(self):
        self.fn, self.actions, self.domains, self.phrases = _import()

    # ── Estructura básica ─────────────────────────────────────────────────────

    def test_returns_string(self):
        r = self.fn("hola")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 0)

    def test_generic_fallback(self):
        r = self.fn("xyz 123 qwerty")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 0)

    def test_short_message(self):
        r = self.fn("ok")
        self.assertIsInstance(r, str)

    def test_first_person_style(self):
        markers = ["voy a", "déjame", "ahora mismo", "un momento", "enseguida",
                   "buscando", "revisando", "analizando", "lanzando", "corriendo",
                   "inspeccionando", "leyendo", "estudiando", "desarrollando",
                   "construyendo", "preparando", "planificando", "depurando",
                   "modificando", "actualizando"]
        for msg in ["bug en código", "crea fichero", "busca símbolo", "git log",
                    "refactoriza módulo", "ejecuta los tests"]:
            r = self.fn(msg).lower()
            self.assertTrue(any(m in r for m in markers), f"No first-person in: {r!r}")

    def test_different_calls_can_vary(self):
        results = {self.fn("xyz 123 qwerty") for _ in range(30)}
        self.assertGreater(len(results), 1)

    # ── Detección de acción ───────────────────────────────────────────────────

    def test_fix_action(self):
        r = self.fn("hay un bug en el código")
        self.assertTrue(any(w in r.lower() for w in
                            ["depurar", "causa raíz", "causa", "raíz", "fallo", "falla", "error", "inspeccion", "leer", "módulo"]), r)

    def test_explain_action(self):
        r = self.fn("explícame cómo funciona este módulo")
        self.assertTrue(any(w in r.lower() for w in
                            ["explicarte", "explicar", "responderte", "estudi", "leyendo", "anali"]), r)

    def test_search_action(self):
        r = self.fn("busca dónde está definido el símbolo en el repositorio")
        self.assertTrue(any(w in r.lower() for w in
                            ["rastrea", "buscando", "buscar", "explorar", "encuentr", "busco", "buscando"]), r)

    def test_refactor_action(self):
        r = self.fn("refactoriza el módulo de autenticación")
        self.assertTrue(any(w in r.lower() for w in
                            ["refactor", "reorganiz", "impacto", "mover", "estructura", "analiz"]), r)

    def test_review_action(self):
        r = self.fn("revisa este código antes de hacer el commit")
        self.assertTrue(any(w in r.lower() for w in
                            ["revis", "analiz", "inspeccion", "leyendo", "audit", "leer"]), r)

    def test_create_action(self):
        r = self.fn("crea una función que valide el email")
        self.assertTrue(any(w in r.lower() for w in
                            ["implementar", "implementa", "construir", "diseñar", "desarrolla", "escribir", "ello"]), r)

    def test_run_action(self):
        r = self.fn("ejecuta los tests ahora")
        self.assertTrue(any(w in r.lower() for w in
                            ["ejecutar", "lanzar", "lanzando", "arranca", "corriendo", "ejecución"]), r)

    def test_update_action(self):
        r = self.fn("actualiza la versión en el fichero de config")
        self.assertTrue(any(w in r.lower() for w in
                            ["actualizar", "modific", "revisar", "leer", "actualiza", "ello"]), r)

    # ── Detección de dominio específico ──────────────────────────────────────

    def test_docker_domain(self):
        r = self.fn("levanta el contenedor con docker-compose")
        self.assertTrue(any(w in r.lower() for w in ["docker", "contenedor"]), r)

    def test_git_domain(self):
        r = self.fn("muéstrame el git log del proyecto")
        self.assertTrue(any(w in r.lower() for w in ["repositorio", "historial", "git", "commit"]), r)

    def test_tests_domain(self):
        r = self.fn("pasa los tests de pytest")
        self.assertTrue(any(w in r.lower() for w in
                            ["test", "suite", "prueba", "ejecutar", "lanzar", "corriendo"]), r)

    def test_docs_domain(self):
        r = self.fn("genera el informe en docx con la plantilla")
        self.assertTrue(any(w in r.lower() for w in
                            ["documento", "plantilla", "generar", "construyendo", "preparando"]), r)

    def test_security_domain(self):
        r = self.fn("audita el código buscando vulnerabilidades de seguridad")
        self.assertTrue(any(w in r.lower() for w in
                            ["seguridad", "vulnerabilidad", "audit", "ataque", "revis"]), r)

    def test_iot_domain(self):
        r = self.fn("configura el dispositivo TAPO en home assistant")
        self.assertTrue(any(w in r.lower() for w in
                            ["dispositivo", "iot", "configurac", "revisar", "revis"]), r)

    def test_config_domain(self):
        r = self.fn("actualiza el oocode.json con los nuevos parámetros")
        self.assertTrue(any(w in r.lower() for w in
                            ["configurac", "parámetro", "config", "actualiz", "modific"]), r)

    # ── Scoring multi-match: dominio más específico gana ─────────────────────

    def test_docker_beats_generic_code(self):
        # "error en docker" debe → fix+docker, no fix+code
        r = self.fn("fix the docker error in the container")
        self.assertTrue(any(w in r.lower() for w in ["docker", "contenedor", "container"]), r)

    def test_tests_beats_run_alone(self):
        # "ejecuta los tests" debe reconocer dominio tests
        r = self.fn("ejecuta los tests de pytest y muéstrame los fallos")
        self.assertTrue(any(w in r.lower() for w in ["test", "suite", "prueba"]), r)

    def test_security_beats_code_in_audit(self):
        # "audita el código en busca de XSS" → security gana sobre code
        r = self.fn("audita el código en busca de vulnerabilidades XSS")
        self.assertTrue(any(w in r.lower() for w in ["seguridad", "vulnerab", "ataque", "audit"]), r)

    # ── Filtro de saludos ─────────────────────────────────────────────────────

    def test_greeting_only_returns_generic(self):
        # Saludo puro (< 8 chars útiles) → no debe mencionar acción específica
        r = self.fn("hola")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 0)

    def test_greeting_plus_task_uses_task(self):
        # "hola, arregla el bug" → fix detectado, no cae en genérico
        r = self.fn("hola, arregla el bug en el código")
        self.assertTrue(any(w in r.lower() for w in
                            ["depurar", "causa", "raíz", "error", "fallo", "falla", "inspeccion", "leer", "módulo"]), r)

    def test_buenos_dias_plus_task(self):
        r = self.fn("buenos días, revisa el fichero de configuración")
        self.assertTrue(any(w in r.lower() for w in
                            ["revis", "analiz", "inspeccion", "configurac", "ello", "leer", "parámetro"]), r)

    # ── Nombre de usuario ─────────────────────────────────────────────────────

    def test_with_user_name_sometimes_includes_name(self):
        results = [self.fn("crea un fichero", "Alex") for _ in range(50)]
        with_name = sum(1 for r in results if "Alex" in r)
        self.assertGreater(with_name, 0)

    def test_without_user_name_no_placeholder(self):
        for _ in range(20):
            r = self.fn("crea un fichero")
            self.assertNotIn("{user}", r)
            self.assertNotIn("Alex", r)

    def test_user_name_no_orphan_placeholder(self):
        for msg in ["crea fichero", "bug en código", "busca símbolo", "xyz"]:
            for _ in range(5):
                r = self.fn(msg, "TestUser")
                self.assertNotIn("{user}", r)
            for _ in range(5):
                r = self.fn(msg, "")
                self.assertNotIn("{user}", r)

    # ── Integridad de la tabla ────────────────────────────────────────────────

    def test_all_action_patterns_compile(self):
        for key, pat in self.actions:
            re.compile(pat)

    def test_all_domain_patterns_compile(self):
        for key, pat in self.domains:
            re.compile(pat)

    def test_all_phrases_are_strings(self):
        for (action, domain), phrases in self.phrases.items():
            for p in phrases:
                self.assertIsInstance(p, str, f"Phrase in ({action},{domain}) is not a string")
                self.assertGreater(len(p), 0)

    def test_all_action_keys_have_generic_fallback(self):
        # Cada acción debe tener al menos un entry con dominio None
        action_keys = {k for k, _ in self.actions}
        for action in action_keys:
            self.assertIn((action, None), self.phrases,
                          f"Missing generic fallback for action '{action}'")

    def test_phrase_keys_reference_valid_actions_and_domains(self):
        valid_actions = {k for k, _ in self.actions} | {None}
        valid_domains = {k for k, _ in self.domains} | {None}
        for (action, domain) in self.phrases:
            self.assertIn(action, valid_actions, f"Unknown action key: {action!r}")
            self.assertIn(domain, valid_domains, f"Unknown domain key: {domain!r}")

    def test_mixed_keywords_returns_string(self):
        r = self.fn("hay un bug en el código y también un fichero docker")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 0)

    def test_long_message_no_specific_keyword(self):
        msg = "necesito " + "algo genérico " * 20
        r = self.fn(msg)
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 0)

    # ── Puerta de confianza: palabra blanda + sin dominio → frase neutral ─────

    def _generic_set(self):
        from agent.loop_helpers import _SINGLE_PREFLIGHT_GENERIC
        return set(_SINGLE_PREFLIGHT_GENERIC)

    def test_soft_run_no_domain_is_neutral(self):
        # "¿qué pasa con esto?" usa 'pasa' (blanda) sin dominio → NO debe prometer
        # ejecución; cae en frase neutral genérica.
        r = self.fn("¿qué pasa con esto exactamente?")
        self.assertNotIn("ejecut", r.lower())
        self.assertNotIn("lanz", r.lower())
        self.assertNotIn("arranc", r.lower())
        self.assertIn(r, self._generic_set())

    def test_soft_create_no_domain_is_neutral(self):
        # "haz un resumen" usa 'haz' (blanda) sin dominio → NO debe prometer
        # implementar/construir; cae en frase neutral.
        r = self.fn("haz un resumen de esto por favor")
        self.assertNotIn("implement", r.lower())
        self.assertNotIn("construir", r.lower())
        self.assertNotIn("desarrolla", r.lower())
        self.assertIn(r, self._generic_set())

    def test_soft_create_with_domain_stays_specific(self):
        # 'haz' (blanda) PERO con dominio web → el dominio respalda la intención,
        # se mantiene la frase específica (no regresión de test_75).
        from agent.loop_helpers import _PF_PHRASES
        r = self.fn("haz crawl de las noticias")
        self.assertIn(r, _PF_PHRASES[("create", "web")], r)

    def test_soft_run_with_domain_stays_specific(self):
        # "pasa los tests" (blanda 'pasa') + dominio tests → frase específica.
        r = self.fn("pasa los tests de pytest")
        self.assertTrue(any(w in r.lower() for w in
                            ["test", "suite", "prueba", "ejecutar", "lanzar"]), r)

    def test_strong_verb_no_domain_stays_specific(self):
        # Verbo FUERTE ('ejecuta') sin dominio → sigue siendo específico (confianza).
        r = self.fn("ejecuta esto ahora mismo")
        self.assertTrue(any(w in r.lower() for w in
                            ["ejecut", "lanz", "arranc", "ejecución"]), r)


if __name__ == "__main__":
    unittest.main()
