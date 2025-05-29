import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from fpdf import FPDF
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import requests

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Visualizador Documentos SSR", layout="wide", page_icon="🔍")

# --- CONFIGURACIÓN GOOGLE DRIVE ---
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_BASE_ID = '1rByjj9IzT6nhUyvnZVJSUMprOWU0axKD'

@st.cache_resource
def conectar_drive():
    if 'GOOGLE_SERVICE_ACCOUNT_JSON' not in st.secrets:
        st.error("⚠️ No se encontró el secret 'GOOGLE_SERVICE_ACCOUNT_JSON'.")
        st.stop()
    service_info = json.loads(st.secrets['GOOGLE_SERVICE_ACCOUNT_JSON'])
    credentials = service_account.Credentials.from_service_account_info(service_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)

service = conectar_drive()

# --- FUNCIONES ---
def descargar_contenido_binario(file_id):
    request = service.files().get_media(fileId=file_id)
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()

def buscar_id_carpeta(nombre, padre_id):
    query = f"name contains '{nombre}' and '{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resultados = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    archivos = resultados.get('files', [])
    return archivos[0]['id'] if archivos else None

def listar_archivos(carpeta_id):
    query = f"'{carpeta_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false"
    archivos = service.files().list(q=query, fields="files(id, name, webViewLink, modifiedTime, size, mimeType)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    return archivos

def formato_peso(bytes_str):
    try:
        b = int(bytes_str)
        if b < 1024:
            return f"{b} B"
        elif b < 1024**2:
            return f"{b/1024:.1f} KB"
        elif b < 1024**3:
            return f"{b/1024**2:.1f} MB"
        else:
            return f"{b/1024**3:.1f} GB"
    except:
        return "-"

def exportar_checklist_estado(checklist_estado):
    filas = []
    for ssr, entregables in checklist_estado.items():
        for item, estado in entregables.items():
            filas.append({"SSR": ssr, "Entregable": item, "Cumplido": "Sí" if estado else "No"})
    return pd.DataFrame(filas)

def generar_pdf_checklist(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Checklist de Entregables SSR", ln=True, align="C")
    pdf.ln(10)
    for index, row in df.iterrows():
        pdf.cell(200, 6, txt=f"{row['SSR']} - {row['Entregable']} - {row['Cumplido']}", ln=True)
    buffer = BytesIO()
    pdf.output(dest='S').encode('latin-1')  # Esto previene error si lo interpretamos directo
    buffer.write(pdf.output(dest='S').encode('latin-1'))
    buffer.seek(0)
    return buffer

# --- CARGA DE DATOS Y AUTENTICACIÓN ---
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a3/Logo_CFC.svg/320px-Logo_CFC.svg.png", width=250)
st.title("🔍 Plataforma de Revisión de Documentos SSR")

try:
    autorizaciones = pd.read_excel("autorizaciones.xlsx")
    estructura = pd.read_excel("estructura_189_proyectos.xlsx")
    checklist_base = pd.read_excel("CHECKLIST ETAPAS.xlsx", header=None).dropna()[0].tolist()
except Exception as e:
    st.error(f"Error cargando archivos base: {e}")
    st.stop()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = ""
    st.session_state.checklist_estado = {}

if not st.session_state.autenticado:
    with st.form("login"):
        usuario = st.text_input("Usuario")
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Ingresar")
        if submitted:
            fila = autorizaciones[(autorizaciones['Usuario'].astype(str).str.strip() == usuario.strip()) &
                                  (autorizaciones['PIN'].astype(str).str.strip() == pin.strip())]
            if fila.empty:
                st.error("Usuario o PIN incorrecto")
            else:
                st.session_state.autenticado = True
                st.session_state.usuario = usuario.strip()
                st.rerun()
else:
    usuario = st.session_state.usuario
    fila = autorizaciones[autorizaciones['Usuario'].astype(str).str.strip() == usuario]
    proyectos = fila['SSR Autorizados'].iloc[0].split(',')
    proyectos = [p.strip() for p in proyectos if p.strip()]
    es_admin = usuario.lower() == 'admin'
    st.session_state.es_admin = es_admin

    st.success(f"Bienvenido {usuario}")
    seleccionado = st.selectbox("Selecciona un SSR:", proyectos)

    if seleccionado not in st.session_state.checklist_estado:
        st.session_state.checklist_estado[seleccionado] = {item: False for item in checklist_base}

    st.markdown("### Checklist del Proyecto")
    for i, item in enumerate(checklist_base):
        st.session_state.checklist_estado[seleccionado][item] = st.checkbox(
            item, value=st.session_state.checklist_estado[seleccionado][item], key=f"{seleccionado}_{i}"
        )

    st.divider()

    if st.session_state.get('es_admin'):
        df_export = exportar_checklist_estado(st.session_state['checklist_estado'])

        st.download_button(
            "📥 Descargar checklist en Excel",
            data=df_export.to_csv(index=False).encode('utf-8'),
            file_name="estado_checklist_ssr.csv",
            mime="text/csv"
        )

        try:
            buffer_pdf = generar_pdf_checklist(df_export)
            st.download_button(
                "📥 Descargar checklist en PDF",
                data=buffer_pdf,
                file_name="estado_checklist_ssr.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"❌ Error al generar PDF: {e}")

    if st.button("Cerrar sesión"):
        st.session_state.autenticado = False
        st.session_state.usuario = ""
        st.rerun()
