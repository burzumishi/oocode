#!/usr/bin/env python3
"""Tests de validación de WebUI OOCode."""
import json
import sys
from pathlib import Path

# Agregar ruta del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from webui.app import app, load_config, save_config, load_state, save_state


@pytest.fixture
def client():
    """Cliente de test para Flask."""
    with app.test_client() as client:
        yield client


class TestWebUI:
    """Tests de la WebUI."""
    
    def test_load_config(self):
        """Test carga de configuración."""
        config = load_config()
        assert isinstance(config, dict)
        assert "models" in config or "model" in config
    
    def test_save_config(self):
        """Test guardado de configuración."""
        config = {"model": "test-model"}
        result = save_config(config)
        assert result is True
    
    def test_load_state(self):
        """Test carga de estado."""
        state = load_state()
        assert isinstance(state, dict)
    
    def test_save_state(self):
        """Test guardado de estado."""
        state = {"running": True, "pid": 1234}
        result = save_state(state)
        assert result is True
    
    def test_app_routes(self, client):
        """Test rutas de la aplicación."""
        # Test página de inicio
        response = client.get('/')
        assert response.status_code == 200
        assert "OOCode WebUI" in response.data.decode('utf-8')
        
        # Test página de configuración
        response = client.get('/config')
        assert response.status_code == 200
        
        # Test página de chat
        response = client.get('/chat')
        assert response.status_code == 200
        
        # Test página de ayuda
        response = client.get('/help')
        assert response.status_code == 200
        
        # Test página de doctor
        response = client.get('/doctor')
        assert response.status_code == 200
        
        # Test página de tema
        response = client.get('/theme')
        assert response.status_code == 200
    
    def test_html_template(self, client):
        """Test plantilla HTML."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar elementos clave
        assert "<html" in html
        assert "<body" in html
        assert "OOCode WebUI" in html
        assert "data-theme" in html  # Tema claro/oscuro
    
    def test_css_variables(self, client):
        """Test variables CSS."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar variables CSS
        assert "--bg-primary" in html
        assert "--text-primary" in html
        assert "--accent-primary" in html
    
    def test_animations(self, client):
        """Test animaciones CSS."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar animaciones
        assert "@keyframes pulse" in html
        assert "@keyframes fadeIn" in html
        assert "@keyframes slideIn" in html
    
    def test_chat_functionality(self, client):
        """Test funcionalidad de chat."""
        response = client.get('/chat')
        html = response.data.decode('utf-8')
        
        # Verificar elementos de chat
        assert "chat-messages" in html
        assert "chat-input" in html
        assert "addMessage" in html
    
    def test_model_selector(self, client):
        """Test selector de modelos."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar selector de modelos
        assert "model-selector" in html or "model-card" in html
    
    def test_theme_toggle(self, client):
        """Test cambio de tema."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar soporte para tema claro
        assert '[data-theme="light"]' in html
    
    def test_nav_links(self, client):
        """Test enlaces de navegación."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar enlaces de navegación
        assert 'href="/"' in html
        assert 'href="/config"' in html
        assert 'href="/chat"' in html
        assert 'href="/help"' in html
        assert 'href="/doctor"' in html
    
    def test_footer(self, client):
        """Test footer."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar footer
        assert "OOCode WebUI" in html
        assert "100% local" in html
    
    def test_help_page(self, client):
        """Test página de ayuda."""
        response = client.get('/help')
        html = response.data.decode('utf-8')
        
        # Verificar comandos documentados
        assert "/agent" in html or "/model" in html
        assert "/hooks" in html or "/plugins" in html
    
    def test_doctor_page(self, client):
        """Test página de doctor."""
        response = client.get('/doctor')
        html = response.data.decode('utf-8')
        
        # Verificar dependencias documentadas
        assert "dependencies" in html or "Flask" in html
    
    def test_webserver_command(self, client):
        """Test comando /webserver."""
        response = client.get('/')
        html = response.data.decode('utf-8')
        
        # Verificar referencia a /webserver
        assert "/webserver" in html or "webserver" in html.lower()


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
