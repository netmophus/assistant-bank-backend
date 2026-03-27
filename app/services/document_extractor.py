import os
import logging
from typing import List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pytesseract  # type: ignore

    pytesseract.pytesseract.tesseract_cmd = (
        os.getenv("RAG_NEW_TESSERACT_CMD")
        or os.getenv("RAG_TESSERACT_CMD")
        or pytesseract.pytesseract.tesseract_cmd
    )
except Exception:
    pytesseract = None


def _ocr_pdf_with_tesseract(file_path: str) -> tuple[str, List[Dict]]:
    enable = (os.getenv("RAG_NEW_ENABLE_OCR", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enable:
        raise ValueError("OCR désactivé")

    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise ValueError("OCR PDF: PyMuPDF (pymupdf) non disponible") from e

    try:
        import pytesseract
        import sys

        tesseract_cmd = (os.getenv("RAG_NEW_TESSERACT_CMD") or "").strip()
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    except ModuleNotFoundError as e:
        import sys

        raise ValueError(
            "OCR PDF: le module 'pytesseract' est introuvable dans cet environnement Python. "
            f"Python utilisé: {sys.executable}. "
            "Installe-le avec: python -m pip install pytesseract pillow"
        ) from e

    ocr_lang = (os.getenv("RAG_NEW_OCR_LANG") or "fra").strip() or "fra"
    max_pages = int((os.getenv("RAG_NEW_OCR_MAX_PAGES") or "30").strip() or "30")
    ocr_dpi = int((os.getenv("RAG_NEW_OCR_DPI") or "300").strip() or "300")

    doc = fitz.open(file_path)
    try:
        full_text_parts: List[str] = []
        chunks: List[Dict] = []

        page_count = len(doc)
        page_limit = min(page_count, max_pages)

        logger.info(
            f"OCR PDF démarré: file={os.path.basename(file_path)} pages_total={page_count} pages_traitées={page_limit} lang={ocr_lang} dpi={ocr_dpi}"
        )

        for i in range(page_limit):
            page = doc[i]
            pix = page.get_pixmap(dpi=ocr_dpi)
            img_bytes = pix.tobytes("png")

            from PIL import Image
            import io

            img = Image.open(io.BytesIO(img_bytes))
            try:
                text = pytesseract.image_to_string(img, lang=ocr_lang)
            except Exception as e:
                msg = str(e)
                if "Error opening data file" in msg or "Failed loading language" in msg:
                    tessdata_prefix = os.getenv("TESSDATA_PREFIX")
                    raise ValueError(
                        "OCR PDF: fichier de langue Tesseract introuvable. "
                        f"Langue demandée: '{ocr_lang}'. "
                        f"TESSDATA_PREFIX={tessdata_prefix!r}. "
                        "Installe le pack de langue (ex: tesseract-ocr-fra) ou ajuste RAG_NEW_OCR_LANG / TESSDATA_PREFIX."
                    ) from e
                raise

            text = (text or "").strip()
            if text:
                full_text_parts.append(text)
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                for para in paragraphs:
                    if len(para) > 50:
                        chunks.append({
                            "content": para,
                            "page_number": i + 1,
                            "section": None,
                        })

        full_text = "\n\n".join(full_text_parts).strip()
        if not full_text or not chunks:
            raise ValueError("OCR PDF: aucun texte détecté")
        logger.info(
            f"OCR PDF terminé: file={os.path.basename(file_path)} chars={len(full_text)} chunks={len(chunks)}"
        )
        return full_text, chunks
    finally:
        doc.close()


async def extract_pdf_content(file_path: str) -> tuple[str, List[Dict]]:
    """
    Extrait le contenu d'un fichier PDF.
    Essaie d'abord PyPDF2, puis PyMuPDF (pymupdf) en fallback.
    Retourne: (texte_complet, liste_de_chunks)
    """
    chunks = []
    full_text = ""
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Le fichier PDF n'existe pas: {file_path}")
    
    # Vérifier la taille du fichier
    file_size = os.path.getsize(file_path)
    logger.info(f"Traitement du PDF: {file_path} (taille: {file_size} bytes)")
    
    # Essayer d'abord avec PyPDF2
    try:
        import PyPDF2
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            
            # Vérifier si le PDF est protégé
            if pdf_reader.is_encrypted:
                logger.warning(f"Le PDF {file_path} est protégé par mot de passe")
                # Essayer de déchiffrer avec un mot de passe vide (certains PDFs ont une protection vide)
                try:
                    pdf_reader.decrypt("")
                except Exception:
                    pass
            
            logger.info(f"PDF contient {num_pages} pages")
            
            if num_pages == 0:
                logger.warning(f"Le PDF {file_path} ne contient aucune page")
                raise ValueError("PDF vide - aucune page trouvée")
            
            pages_with_text = 0
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                try:
                    text = page.extract_text()
                    if text and text.strip():
                        pages_with_text += 1
                        full_text += text + "\n\n"
                        # Découper en chunks (paragraphes)
                        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                        for para in paragraphs:
                            if len(para) > 50:  # Ignorer les très petits paragraphes
                                chunks.append({
                                    "content": para,
                                    "page_number": page_num,
                                    "section": None,
                                })
                except Exception as page_error:
                    logger.warning(f"Erreur lors de l'extraction de la page {page_num} avec PyPDF2: {page_error}")
                    continue
            
            logger.info(f"PyPDF2: {pages_with_text}/{num_pages} pages avec du texte extrait")
        
        # Si PyPDF2 a réussi à extraire du contenu, retourner
        if full_text.strip() and chunks:
            logger.info(f"Extraction réussie avec PyPDF2: {len(chunks)} chunks extraits")
            return full_text, chunks
        
        # Si PyPDF2 n'a rien extrait, essayer PyMuPDF
        logger.info(f"PyPDF2 n'a pas extrait de contenu, essai avec PyMuPDF pour {file_path}")
        
    except ImportError:
        logger.info("PyPDF2 non disponible, essai avec PyMuPDF")
    except Exception as e:
        logger.warning(f"Erreur avec PyPDF2: {e}, essai avec PyMuPDF")
    
    # Essayer avec PyMuPDF (pymupdf) - plus robuste
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(file_path)
        num_pages = len(doc)
        
        # Vérifier si le PDF nécessite un mot de passe
        if doc.needs_pass:
            logger.warning(f"Le PDF {file_path} nécessite un mot de passe")
            doc.close()
            raise ValueError(
                f"Le PDF est protégé par mot de passe. "
                f"Veuillez déverrouiller le PDF avant de l'uploader."
            )
        
        logger.info(f"PyMuPDF: PDF contient {num_pages} pages")
        
        if num_pages == 0:
            logger.warning(f"Le PDF {file_path} ne contient aucune page")
            doc.close()
            raise ValueError("PDF vide - aucune page trouvée")
        
        pages_with_text = 0
        pages_with_images = 0
        
        for page_num in range(num_pages):
            try:
                page = doc[page_num]
                text = page.get_text()
                
                # Vérifier si la page contient des images
                image_list = page.get_images()
                if image_list:
                    pages_with_images += 1
                
                if text and text.strip():
                    pages_with_text += 1
                    full_text += text + "\n\n"
                    # Découper en chunks (paragraphes)
                    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                    for para in paragraphs:
                        if len(para) > 50:  # Ignorer les très petits paragraphes
                            chunks.append({
                                "content": para,
                                "page_number": page_num + 1,
                                "section": None,
                            })
            except Exception as page_error:
                logger.warning(f"Erreur lors de l'extraction de la page {page_num + 1} avec PyMuPDF: {page_error}")
                continue
        
        doc.close()
        
        logger.info(f"PyMuPDF: {pages_with_text}/{num_pages} pages avec du texte, {pages_with_images} pages avec images")

        enable_ocr = (os.getenv("RAG_NEW_ENABLE_OCR", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}
        force_ocr_if_images = (os.getenv("RAG_NEW_OCR_FORCE_IF_IMAGES", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}
        min_text_pages_for_skip = int((os.getenv("RAG_NEW_OCR_MIN_TEXT_PAGES", "1") or "1").strip() or "1")

        if enable_ocr and force_ocr_if_images and pages_with_images > 0 and pages_with_text <= min_text_pages_for_skip:
            try:
                logger.info(f"PyMuPDF a détecté des images; tentative d'OCR complémentaire pour {file_path}")
                ocr_text, ocr_chunks = _ocr_pdf_with_tesseract(file_path)
                if ocr_text and ocr_text.strip():
                    full_text = (full_text + "\n\n" + ocr_text).strip()
                if ocr_chunks:
                    chunks.extend(ocr_chunks)
            except Exception as ocr_error:
                logger.warning(f"OCR complémentaire ignoré: {ocr_error}")
        
        # Si PyMuPDF a réussi à extraire du contenu, retourner
        if full_text.strip() and chunks:
            logger.info(f"Extraction réussie avec PyMuPDF: {len(chunks)} chunks extraits")
            return full_text, chunks
        
    except ImportError:
        logger.warning("PyMuPDF (pymupdf) n'est pas installé. Installez-le avec: pip install pymupdf")
    except ValueError as ve:
        # Re-lancer les ValueError (PDF protégé, vide, etc.)
        raise
    except Exception as e:
        logger.error(f"Erreur avec PyMuPDF: {e}")
    
    # Si aucun des deux n'a fonctionné
    if not full_text.strip() and not chunks:
        # Construire un message d'erreur détaillé
        diagnostic_info = []
        
        try:
            import fitz
            doc = fitz.open(file_path)
            num_pages = len(doc)
            has_images = False
            for page_num in range(min(num_pages, 5)):  # Vérifier les 5 premières pages
                page = doc[page_num]
                if page.get_images():
                    has_images = True
                    break
            doc.close()
            
            if has_images and num_pages > 0:
                diagnostic_info.append(f"Le PDF contient {num_pages} pages avec des images")
                diagnostic_info.append("mais aucun texte extractible")
        except Exception:
            pass
        
        # Si le PDF semble scanné (images) on tente un OCR en fallback
        if diagnostic_info:
            try:
                ocr_text, ocr_chunks = _ocr_pdf_with_tesseract(file_path)
                logger.info(f"OCR fallback réussi: {len(ocr_chunks)} chunks extraits")
                return ocr_text, ocr_chunks
            except Exception as ocr_err:
                logger.warning(f"OCR fallback échoué: {ocr_err}")

        error_msg = f"Aucun texte n'a pu être extrait du PDF '{os.path.basename(file_path)}'. "
        
        if diagnostic_info:
            error_msg += " ".join(diagnostic_info) + ". "
        
        error_msg += (
            "Causes possibles:\n"
            "- Le PDF est scanné (image uniquement) → nécessite un OCR\n"
            "- Le PDF est protégé par mot de passe → déverrouillez-le avant l'upload\n"
            "- Le PDF est corrompu → vérifiez l'intégrité du fichier\n"
            "- Le PDF contient seulement des images sans texte → utilisez un outil OCR"
        )
        
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    return full_text, chunks


async def extract_word_content(file_path: str) -> tuple[str, List[Dict]]:
    """
    Extrait le contenu d'un fichier Word (.docx).
    Retourne: (texte_complet, liste_de_chunks)
    """
    try:
        from docx import Document
        
        chunks = []
        full_text = ""
        
        doc = Document(file_path)
        
        current_section = None
        current_paragraphs = []
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            # Détecter les titres (style Heading)
            if para.style.name.startswith('Heading'):
                # Sauvegarder le paragraphe précédent comme chunk
                if current_paragraphs:
                    chunks.append({
                        "content": "\n".join(current_paragraphs),
                        "page_number": None,
                        "section": current_section,
                    })
                    current_paragraphs = []
                current_section = text
                full_text += f"\n\n## {text}\n\n"
            else:
                current_paragraphs.append(text)
                full_text += text + "\n"
        
        # Ajouter le dernier chunk
        if current_paragraphs:
            chunks.append({
                "content": "\n".join(current_paragraphs),
                "page_number": None,
                "section": current_section,
            })
        
        return full_text, chunks
    except ImportError:
        logger.error("python-docx n'est pas installé. Installez-le avec: pip install python-docx")
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction Word: {e}")
        raise


async def extract_excel_content(file_path: str) -> tuple[str, List[Dict]]:
    """
    Extrait le contenu d'un fichier Excel (.xlsx, .xls).
    Retourne: (texte_complet, liste_de_chunks)
    """
    try:
        import pandas as pd
        
        chunks = []
        full_text = ""
        
        # Lire toutes les feuilles
        excel_file = pd.ExcelFile(file_path)
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Convertir en texte structuré
            sheet_text = f"\n\n=== Feuille: {sheet_name} ===\n\n"
            sheet_text += df.to_string(index=False)
            full_text += sheet_text + "\n\n"
            
            # Créer un chunk par feuille
            chunks.append({
                "content": sheet_text,
                "page_number": None,
                "section": sheet_name,
            })
        
        return full_text, chunks
    except ImportError:
        logger.error("pandas n'est pas installé. Installez-le avec: pip install pandas openpyxl")
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction Excel: {e}")
        raise


async def extract_image_content(file_path: str) -> tuple[str, List[Dict]]:
    """
    Extrait le contenu d'une image en utilisant l'OCR (Optical Character Recognition).
    Nécessite pytesseract et Tesseract OCR installé sur le système.
    """
    chunks = []
    full_text = ""
    
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning("PIL ou pytesseract non disponible. L'extraction de texte depuis les images nécessite ces bibliothèques.")
        raise ValueError(
            "L'extraction de texte depuis les images nécessite PIL (Pillow) et pytesseract. "
            "Installez-les avec: pip install Pillow pytesseract"
        )
    
    try:
        # Ouvrir l'image
        image = Image.open(file_path)
        
        # Extraire le texte avec OCR
        text = pytesseract.image_to_string(image, lang='fra+eng')  # Français et Anglais
        
        if not text or not text.strip():
            logger.warning(f"Aucun texte détecté dans l'image {file_path}")
            raise ValueError("Aucun texte détecté dans l'image. L'image peut être vide ou nécessiter un meilleur contraste.")
        
        full_text = text.strip()
        
        # Découper en chunks (paragraphes)
        paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
        for para in paragraphs:
            if len(para) > 50:  # Ignorer les très petits paragraphes
                chunks.append({
                    "content": para,
                    "page_number": None,
                    "section": None,
                })
        
        logger.info(f"Extraction OCR réussie: {len(chunks)} chunks extraits de l'image")
        return full_text, chunks
        
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction OCR de l'image {file_path}: {e}")
        raise ValueError(f"Erreur lors de l'extraction de texte depuis l'image: {str(e)}")


async def extract_document_content(file_path: str, file_type: str) -> tuple[str, List[Dict]]:
    """
    Extrait le contenu d'un document selon son type.
    """
    if file_type == "pdf":
        return await extract_pdf_content(file_path)
    elif file_type in ["word", "docx"]:
        return await extract_word_content(file_path)
    elif file_type in ["excel", "xlsx", "xls"]:
        return await extract_excel_content(file_path)
    elif file_type == "image":
        return await extract_image_content(file_path)
    else:
        raise ValueError(f"Type de fichier non supporté: {file_type}")


def split_into_chunks(text: str, max_chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Découpe un texte en chunks avec overlap pour préserver le contexte.
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_chunk_size
        
        # Si ce n'est pas la fin, essayer de couper à un espace ou retour à la ligne
        if end < len(text):
            # Chercher le dernier espace ou retour à la ligne avant la limite
            last_space = text.rfind(' ', start, end)
            last_newline = text.rfind('\n', start, end)
            cut_point = max(last_space, last_newline)
            
            if cut_point > start:
                end = cut_point
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Avancer avec overlap
        start = end - overlap if end < len(text) else end
    
    return chunks

