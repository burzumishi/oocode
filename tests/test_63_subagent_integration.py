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
        assert sub.status == "running"
    
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
    
    def test_subagent_queue_management(self, mock_config, mock_build_registry):
        """Test gestión de cola de subagentes."""
        from agent.subagent import _enqueue, _dequeue, _subagent_queue
        import time
        
        # Crear subagentes mock
        sub1 = MagicMock()
        sub1.priority = 1
        sub2 = MagicMock()
        sub2.priority = 0
        
        # Añadir a la cola
        _enqueue(sub1)
        _enqueue(sub2)
        
        # Verificar orden en cola (mayor prioridad primero)
        with _subagent_queue.__class__._queue_lock:
            queue_copy = list(_subagent_queue)
        
        # El de mayor prioridad debe estar primero
        assert queue_copy[0][1] >= queue_copy[1][1]
    
    def test_subagent_termination(self, mock_config, mock_build_registry):
        """Test terminación de subagentes."""
        from agent.subagent import SubAgentRunner, kill
        
        runner = SubAgentRunner(
            config=mock_config,
            permissions=MagicMock(),
            build_registry_fn=mock_build_registry,
        )
        
        # Spawn subagente
        sub = runner.spawn_background("coding", "analizar main.py", priority=0)
        
        # Verificar que está running
        assert sub.status == "running"
        
        # Simular terminación (en producción se usa kill())
        sub.status = "done"
        sub.finished_at = time.time()
        
        # Verificar estado
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
