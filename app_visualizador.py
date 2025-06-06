import streamlit as st
import pandas as pd
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(layout="wide")

# CONFIGURACIÓN GOOGLE DRIVE
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_BASE_ID = '1rByjj9IzT6nhUyvnZVJSUMprOWU0axKD'

@st.cache_resource
def conectar_drive():
    if not os.path.exists("service_account.json"):
        st.error("No se encontró el archivo de credenciales. Asegúrate de que 'service_account.json' esté en la misma carpeta del script.")
        st.stop()

    with open("service_account.json") as source:
        service_info = json.load(source)

    credentials = service_account.Credentials.from_service_account_info(
        service_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)

service = conectar_drive()

def buscar_id_carpeta(nombre, padre_id):
    query = f"name contains '{nombre}' and '{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
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
        fields="files(id, name, webViewLink, modifiedTime, size)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute().get('files', [])
    return archivos

# INTERFAZ STREAMLIT
st.image("logo_cfc.png", width=250)
st.title("🔍 Plataforma de Revisión de Documentos SSR")

# --- Autenticación ---
if not os.path.exists("autorizaciones.xlsx"):
    st.error("No se encontró el archivo 'autorizaciones.xlsx'. Asegúrate de que esté en la misma carpeta del script.")
    st.stop()

if not os.path.exists("estructura_189_proyectos.xlsx"):
    st.error("No se encontró el archivo 'estructura_189_proyectos.xlsx'. Asegúrate de que esté en la misma carpeta del script.")
    st.stop()

autorizaciones = pd.read_excel("autorizaciones.xlsx", sheet_name=0)
proyectos_nombres = pd.read_excel("estructura_189_proyectos.xlsx", sheet_name="Listado SSR")
diccionario_nombres = dict(zip(proyectos_nombres['Código'].astype(str).str.strip(), proyectos_nombres['Nombre Completo'].astype(str).str.strip()))

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = ""

if not st.session_state.autenticado:
    with st.form("login_form"):
        usuario = st.text_input("Ingrese su usuario:")
        pin = st.text_input("Ingrese su PIN:", type="password")
        login = st.form_submit_button("Ingresar")

    if login:
        if not ((autorizaciones['Usuario'].astype(str).str.strip() == usuario.strip()) & (autorizaciones['PIN'].astype(str).str.strip() == pin.strip())).any():
            st.error("Usuario o PIN incorrecto.")
            st.stop()

        st.session_state.autenticado = True
        st.session_state.usuario = usuario.strip()
        st.rerun()

if st.session_state.autenticado:
    usuario = st.session_state.usuario
    proyectos_raw = autorizaciones[autorizaciones['Usuario'].astype(str).str.strip() == usuario]['SSR Autorizados'].iloc[0]
    opciones_dict = {f"{p.strip()} - {diccionario_nombres.get(p.strip(), '')}": p.strip() for p in proyectos_raw.split(',') if p.strip()}
    opciones_ordenadas = dict(sorted(opciones_dict.items()))

    st.success(f"Acceso autorizado para {usuario}.")
    proyecto_label = st.selectbox("Selecciona un proyecto autorizado:", list(opciones_ordenadas.keys()))

    if proyecto_label:
        codigo_base = opciones_ordenadas[proyecto_label]
        id_proyecto = buscar_id_carpeta(codigo_base, FOLDER_BASE_ID)
        if not id_proyecto:
            st.warning("No se encontró la carpeta del proyecto en Drive.")
            st.stop()

        subcarpetas = service.files().list(
            q=f"'{id_proyecto}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute().get('files', [])

        subcarpetas = sorted(subcarpetas, key=lambda x: x['name'])

        for sub in subcarpetas:
            with st.expander(f"📂 {sub['name']}"):
                archivos = listar_archivos(sub['id'])

                if not archivos:
                    st.info("No hay archivos en esta carpeta.")
                else:
                    filtro = st.text_input(f"🔎 Buscar archivos en '{sub['name']}'", key=sub['id'])
                    archivos_filtrados = [f for f in archivos if filtro.lower() in f['name'].lower()]

                    df = pd.DataFrame([{
                        'Archivo': f["name"],
                        'Enlace': f"[Abrir]({f['webViewLink']})",
                        'Tamaño (kB)': round(int(f.get('size', 0)) / 1024, 1) if 'size' in f else '—',
                        'Última modificación': f.get('modifiedTime', '—')[:10]
                    } for f in archivos_filtrados])

                    st.dataframe(df, use_container_width=True)

                    st.download_button(
                        label=f"📥 Descargar listado '{sub['name']}'",
                        data=df.to_csv(index=False).encode('utf-8'),
                        file_name=f"listado_{sub['name']}.csv",
                        mime='text/csv',
                        key=f"desc_{sub['id']}"
                    )
