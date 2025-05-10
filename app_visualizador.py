import streamlit as st
import pandas as pd
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# CONFIGURACIÓN GOOGLE DRIVE
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_BASE_ID = '1rByjj9IzT6nhUyvnZVJSUMprOWU0axKD'

@st.cache_resource
def conectar_drive():
    service_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(
        service_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)

service = conectar_drive()

def buscar_id_carpeta(nombre, padre_id):
    query = f"name='{nombre}' and '{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resultados = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    archivos = resultados.get('files', [])
    return archivos[0]['id'] if archivos else None

def listar_archivos(carpeta_id):
    query = f"'{carpeta_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false"
    archivos = service.files().list(
        q=query,
        fields="files(id, name, webViewLink)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute().get('files', [])
    return archivos

# INTERFAZ STREAMLIT
st.set_page_config(layout="wide")
st.title("🔍 Plataforma de Revisión de Documentos SSR")

# --- Autenticación ---
autorizaciones = pd.read_excel("autorizaciones.xlsx")
usuario = st.text_input("Ingrese su usuario:")
pin = st.text_input("Ingrese su PIN:", type="password")

if usuario and pin:
    if not ((autorizaciones['Usuario'] == usuario) & (autorizaciones['PIN'] == pin)).any():
        st.error("Usuario o PIN incorrecto.")
        st.stop()

    proyectos_autorizados = autorizaciones[autorizaciones['Usuario'] == usuario]['SSR Autorizados'].iloc[0].split(',')
    proyectos_autorizados = [p.strip() for p in proyectos_autorizados]

    st.success(f"Acceso autorizado para {usuario}.")
    proyecto = st.selectbox("Selecciona un proyecto autorizado:", proyectos_autorizados)

    if proyecto:
        id_proyecto = buscar_id_carpeta(proyecto, FOLDER_BASE_ID)
        if not id_proyecto:
            st.warning("No se encontró la carpeta del proyecto en Drive.")
            st.stop()

        subcarpetas = service.files().list(
            q=f"'{id_proyecto}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute().get('files', [])

        for sub in subcarpetas:
            st.markdown(f"### 📂 {sub['name']}")
            archivos = listar_archivos(sub['id'])
            for f in archivos:
                st.markdown(f"- [{f['name']}]({f['webViewLink']})")
