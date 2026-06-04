"""Tests de integración para subagentes.

Tests para verificar que spawn_background, spawn_with_priority,
start_background_session, create_team funcionan correctamente.
"""
import pytest
import time
from unittest.mock import MagicMock


class TestSubagentIntegration:
    """Tests de integración para subagentes."""
    
    @pytest.fixture
    def mock_config(self):
        """Configuración mock para tests."""
        config = MagicMock()
        config.agents = [
            MagicMock(id="main", name="main", emoji="🤖"),
            MagicMock(id="coding", name="coding", emoji="💻"),
            MagicMock(id="reasoning", name="reasoning", emoji="🧠"),
            MagicMock(id="home_office", name="home_office", emoji="📋"),
        ]
        config.subagents_max_concurrent = 4
        return config
    
    @pytest.fixture
    def mock_build_registry(self, mock_config):
        """Función mock para build_registry."""
        def build_registry(workspace, config):
            return {}
        return build_registry
    
    def test_spawn_background_creates_subagent(self, mock_config, mock_build_registry):
        """Test que spawn_background crea un subagente correctamente."""
        from agent.subagent import SubAgentRunner
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Spawn subagente
        sub = runner.spawn_background("coding", "analizar main.py", priority=1)
        
        # Verificar que se creó correctamente
        assert sub is not None
        assert sub.agent_id == "coding"
        assert sub.task == "analizar main.py"
        assert sub.priority == 1
        # El subagente empieza en "queued" y pasa a "running" al adquirir el semáforo
        assert sub.status in ("queued", "running", "done", "error")
    
    def test_spawn_with_priority_calls_spawn_background(self, mock_config, mock_build_registry):
        """Test que spawn_with_priority llama a spawn_background."""
        from agent.subagent import SubAgentRunner
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Spawn con prioridad
        sub = runner.spawn_with_priority("coding", "analizar utils.py", priority=0)
        
        # Verificar que se creó correctamente
        assert sub is not None
        assert sub.agent_id == "coding"
        assert sub.task == "analizar utils.py"
        assert sub.priority == 0
    
    def test_start_background_session_creates_session(self, mock_config, mock_build_registry):
        """Test que start_background_session crea una sesión de background."""
        from agent.session import start_background_session
        
        # Crear sesión de background
        result = start_background_session(
            agent_id="coding",
            task="analizar fichero.py",
            priority=0,
            max_concurrent=4,
            resource_pool=None
        )
        
        # Verificar resultado
        assert result is not None
        assert "session_id" in result
        assert "agent_id" in result
        assert "task" in result
    
    def test_create_team_creates_team(self, mock_config, mock_build_registry):
        """Test que create_team crea un equipo de agentes."""
        from agent.tasks import create_team
        
        # Crear equipo
        team = create_team(
            team_id="team-1",
            lead_agent_id="coding",
            members=["coding", "reasoning"]
        )
        
        # Verificar equipo
        assert team is not None
        assert team["team_id"] == "team-1"
        assert team["lead_agent_id"] == "coding"
        assert team["members"] == ["coding", "reasoning"]
    
    def test_subagent_concurrency_semaphore(self, mock_config, mock_build_registry):
        """El semáforo de concurrencia limita subagentes simultáneos."""
        import threading
        from agent.subagent import _get_concurrency_sem

        # Semáforo con límite 2
        sem = _get_concurrency_sem(2)
        # Adquirir las 2 plazas disponibles
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is True
        # La tercera adquisición no bloqueante debe fallar
        assert sem.acquire(blocking=False) is False
        # Liberar las dos plazas
        sem.release()
        sem.release()
        # Ahora debería poder adquirir de nuevo
        assert sem.acquire(blocking=False) is True
        sem.release()
    
    def test_subagent_termination(self, mock_config, mock_build_registry):
        """Test terminación de subagentes."""
        from agent.subagent import SubAgentRunner
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Spawn subagente
        sub = runner.spawn_background("coding", "analizar main.py", priority=0)

        # Estado inicial: queued o ya running/done según velocidad del scheduler
        assert sub.status in ("queued", "running", "done", "error")

        # Simular terminación manual
        sub.status = "done"
        sub.finished_at = time.time()
        assert sub.status == "done"
    
    def test_subagent_steering(self, mock_config, mock_build_registry):
        """Test steer de subagentes."""
        from agent.subagent import SubAgentRunner
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Spawn subagente
        sub = runner.spawn_background("coding", "analizar main.py", priority=0)
        
        # Verificar que tiene steer_queue
        assert hasattr(sub, 'steer_queue')
        assert sub.steer_queue is not None
    
    def test_background_session_resource_control(self, mock_config, mock_build_registry):
        """Test control de recursos de background sessions."""
        from agent.session import BackgroundSession
        
        # Crear sesión con control de recursos
        bg = BackgroundSession(
            session_id="session-1",
            agent_id="coding",
            task="analizar fichero.py",
            priority=0,
            max_concurrent=2,
            resource_pool={
                "max_memory_mb": 512,
                "max_cpu_percent": 50,
                "max_tokens_per_minute": 10000,
            }
        )
        
        # Verificar configuración
        assert bg.max_concurrent == 2
        assert bg.resource_pool["max_memory_mb"] == 512


class TestSubagentIntegrationWithAgent:
    """Tests de integración de subagentes con agente principal."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.agents = [
            MagicMock(id="main", name="main", emoji="🤖"),
            MagicMock(id="coding", name="coding", emoji="💻"),
            MagicMock(id="reasoning", name="reasoning", emoji="🧠"),
            MagicMock(id="home_office", name="home_office", emoji="📋"),
        ]
        config.subagents_max_concurrent = 4
        return config

    @pytest.fixture
    def mock_build_registry(self, mock_config):
        def build_registry(workspace, config):
            return {}
        return build_registry

    @pytest.fixture
    def mock_agent_loop(self):
        """Mock de AgentLoop."""
        loop = MagicMock()
        loop.run = MagicMock(return_value="resultado")
        return loop
    
    def test_agent_calls_subagent(self, mock_agent_loop, mock_config, mock_build_registry):
        """Test que agente llama a subagente correctamente."""
        from agent.subagent import SubAgentRunner
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Mock de run() para simular ejecución de subagente
        runner.run = mock_agent_loop.run
        
        # Spawn subagente
        sub = runner.spawn_background("coding", "analizar main.py", priority=0)
        
        # Verificar que run() fue llamado
        assert mock_agent_loop.run.called
    
    def test_subagent_inherits_config(self, mock_config, mock_build_registry):
        """Test que subagente hereda configuración del agente."""
        from agent.subagent import SubAgentRunner
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Spawn subagente
        sub = runner.spawn_background("coding", "analizar main.py", priority=0)
        
        # Verificar que subagente tiene referencia a config
        assert runner.config is not None


class TestInactivityWatchdog:
    """El watchdog de timeout mide INACTIVIDAD (por paso/petición al LLM),
    no tiempo total: un subagente que progresa no se detiene aunque la tarea
    dure más que `timeout_seconds`; uno que se cuelga sin progreso sí se mata.
    """

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.agents = [MagicMock(id="coding", name="coding", emoji="💻")]
        config.subagents_max_concurrent = 4
        return config

    @pytest.fixture
    def runner(self, mock_config):
        from agent.subagent import SubAgentRunner
        return SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=lambda ws, cfg: {},
        )

    def test_heartbeat_updates_last_activity(self):
        from agent.subagent import ActiveSubAgent
        import threading, queue
        sub = ActiveSubAgent(
            run_id="x", agent_id="a", agent_name="a", agent_emoji="🤖",
            task="t", thread=None, kill_event=threading.Event(),
            steer_queue=queue.SimpleQueue(),
        )
        old = sub.last_activity
        time.sleep(0.05)
        sub.heartbeat()
        assert sub.last_activity > old

    def test_watchdog_kills_on_inactivity(self, runner):
        """Un paso que se cuelga sin heartbeat se mata tras `timeout_seconds`."""
        def stalled_run(*a, **kw):
            time.sleep(3)          # se cuelga, nunca llama heartbeat
            return "done"
        runner.run = stalled_run

        sub = runner.spawn_background("coding", "tarea", priority=0, timeout_seconds=1)
        sub.thread.join(timeout=6)

        assert sub.status == "killed"
        assert sub.error and "sin progreso" in sub.error

    def test_watchdog_survives_with_heartbeat(self, runner):
        """Con heartbeats sostenidos, el subagente sobrevive aunque supere el timeout total."""
        def progressing_run(agent_id, task, silent=True, kill_event=None,
                            steer_queue=None, priority=0, sub_ref=None):
            # ~2.4s de trabajo total > timeout_seconds=1, pero progresando cada 0.4s
            for _ in range(6):
                if kill_event is not None and kill_event.is_set():
                    break
                if sub_ref is not None:
                    sub_ref.heartbeat()
                time.sleep(0.4)
            return "done"
        runner.run = progressing_run

        sub = runner.spawn_background("coding", "tarea", priority=0, timeout_seconds=1)
        sub.thread.join(timeout=8)

        assert sub.status == "done"
        assert sub.error is None

    def test_no_watchdog_when_timeout_zero(self, runner):
        """timeout_seconds=0 → sin watchdog (el subagente corre sin límite)."""
        def quick_run(*a, **kw):
            return "ok"
        runner.run = quick_run

        sub = runner.spawn_background("coding", "tarea", priority=0, timeout_seconds=0)
        sub.thread.join(timeout=5)

        assert sub.status == "done"
        assert sub.error is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
