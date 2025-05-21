import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from fpdf import FPDF
from io import BytesIO
from PIL import Image
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

# --- FUNCIONES DE GOOGLE DRIVE ---

def generar_csv_pendientes(resumen):
    filas = []
    for codigo, label, _, _, _, pendientes in resumen:
        for item in pendientes:
            filas.append({
                "Código SSR": codigo,
                "Nombre Proyecto": label,
                "Entregable Pendiente": item
            })
    return pd.DataFrame(filas)

def buscar_id_carpeta(nombre, padre_id):
    query = f"name contains '{nombre}' and '{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resultados = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    archivos = resultados.get('files', [])
    return archivos[0]['id'] if archivos else None

def listar_archivos(carpeta_id):
    query = f"'{carpeta_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false"
    archivos = service.files().list(q=query, fields="files(id, name, webViewLink, modifiedTime, size, mimeType)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    return archivos

# --- CARGA DE DATOS Y AUTENTICACIÓN ---
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a3/Logo_CFC.svg/320px-Logo_CFC.svg.png", width=250)
st.title("🔍 Plataforma de Revisión de Documentos SSR")

try:
    autorizaciones = pd.read_excel("autorizaciones.xlsx")
    autorizaciones['Usuario'] = autorizaciones['Usuario'].astype(str).str.strip()
    autorizaciones['PIN'] = autorizaciones['PIN'].astype(str).str.strip()
    autorizaciones['SSR Autorizados'] = autorizaciones['SSR Autorizados'].astype(str).str.strip()
    autorizaciones['SSR Autorizados'] = autorizaciones['SSR Autorizados'].replace('nan', '')
    autorizaciones['SSR Autorizados'] = autorizaciones['SSR Autorizados'].apply(
        lambda x: ','.join([s.strip() for s in x.split(',') if s.strip()]) if isinstance(x, str) else ''
    )
except Exception as e:
    st.error(f"Error al cargar archivos: {e}")
    st.stop()

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
    usuario_data = autorizaciones[autorizaciones['Usuario'].astype(str).str.strip() == usuario]
    if usuario_data.empty:
        st.error("⚠️ Usuario no autorizado o sin proyectos asignados.")
        st.stop()

    ssr_autorizados = usuario_data['SSR Autorizados'].dropna()
    if ssr_autorizados.empty:
        st.error("⚠️ El usuario no tiene SSR autorizados asignados.")
        st.stop()

    try:
        st.write("✅ SSR autorizados encontrados:", ssr_autorizados.tolist())
        proyectos_raw = ssr_autorizados.iloc[0] if not ssr_autorizados.empty else ""
    except IndexError:
        st.error("⚠️ No hay SSR asignados válidos para este usuario.")
        st.stop()

    if not isinstance(proyectos_raw, str) or not any(p.strip() for p in proyectos_raw.split(',')):
        st.error("⚠️ No hay SSR asignados válidos para este usuario.")
        st.stop()

    st.write("⚠️ Modo seguro: funciones deshabilitadas hasta cargar estructura completa correctamente.")

    # --- CARGA DE ESTRUCTURA DE PROYECTOS ---
    try:
        estructura = pd.read_excel("estructura_189_proyectos.xlsx")
        st.subheader("📂 Estructura cargada")
        st.dataframe(estructura.head())
    except Exception as e:
        st.error(f"Error al cargar estructura: {e}")
