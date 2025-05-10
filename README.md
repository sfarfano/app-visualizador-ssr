
# Plataforma de Revisión de Documentos SSR

Esta aplicación permite a los Inspectores Fiscales revisar en tiempo real los documentos cargados por el equipo técnico, con acceso restringido por proyecto.

## 🚀 Cómo usar

1. Ejecuta la app en [Streamlit Cloud](https://streamlit.io/cloud) o localmente con:
   ```
   streamlit run app_visualizador.py
   ```

2. Ingresa tu **usuario y PIN** registrados en el archivo `autorizaciones.xlsx`.

3. Selecciona uno de los proyectos habilitados para tu usuario.

4. Visualiza y descarga archivos directamente desde Google Drive según la estructura del proyecto.

## 📁 Estructura del Proyecto

- `app_visualizador.py`: Script principal de la app.
- `autorizaciones.xlsx`: Lista de usuarios, PIN y proyectos habilitados.
- `estructura_final_189_proyectos.xlsx`: Referencia cruzada para la carga de documentos.
- `requirements.txt`: Dependencias de Python.

## 🔐 Seguridad

- Cada usuario tiene acceso solo a los proyectos (SSR) autorizados en `autorizaciones.xlsx`.
- Los archivos se leen desde Google Drive en modo de solo lectura (`drive.readonly`).

## 📦 Dependencias

Incluir este contenido en `requirements.txt`:

```
streamlit
pandas
google-api-python-client
google-auth
google-auth-oauthlib
openpyxl
```

## 🛠 Cómo desplegar en Streamlit Cloud

1. Sube los archivos a un repositorio en GitHub.
2. Entra a [Streamlit Cloud](https://streamlit.io/cloud) y conecta tu repositorio.
3. Establece `app_visualizador.py` como archivo principal.
4. En la sección `Secrets`, agrega tu clave de cuenta de servicio como:

```toml
GOOGLE_SERVICE_ACCOUNT_JSON = """{ ... tu JSON ... }"""
```

## 👤 Contacto técnico

Soledad Farfán Ortiz  
CFC Ingeniería Ltda.
