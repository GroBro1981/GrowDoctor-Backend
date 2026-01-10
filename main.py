import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:http_parser/http_parser.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // ⏳ Splash Screen bewusst verlängern (z. B. 2,5 Sekunden)
  await Future.delayed(const Duration(milliseconds: 2500));

  runApp(const GrowDoctorBetaApp());
}

/// ---------------------------------------------
/// GrowDoctor BETA (Diagnose + Settings)
/// Enthält:
/// - Nicht-umgehbarer AgeGate (18+) mit explizitem Text
/// - Disclaimer/Legal (nicht-umgehbar, einmalig bestätigen)
/// - Datenschutz/Feedback/Kontakt Seiten
/// - Foto-Details: Bildposition + Bildart (Dropdowns)
/// - Timeout 120s
/// - Loading-Text "GrowDoctor analysiert…"
/// - Same-image Erkennung + Nachfrage ("trotzdem analysieren?") -> force=true
/// - Feedback nach Analyse: 👍/👎 + optional Text
/// - Anonymes Tracking (store-safe) via /metrics (optional; Fehler werden ignoriert)
/// ---------------------------------------------

// ======================
// CONFIG (BETA)
// ======================
const String APP_TITLE = 'GrowDoctor Beta';
const String SUPPORT_EMAIL = 'growdoctor.app@gmail.com';

// ✅ BETA Backend
const String BASE_URL = 'https://growdoctor-backend-beta.onrender.com';

// Endpoints
const String DIAGNOSE_PATH = '/diagnose';
const String METRICS_PATH = '/metrics';

// Timeout (wie besprochen)
const Duration REQUEST_TIMEOUT = Duration(seconds: 120);

// Timeout-Text (wie du wolltest)
const String TIMEOUT_FALLBACK_DE =
    'Das Bild muss genauer analysiert werden. Bitte lade es erneut hoch.';

// Anonyme Client-ID
const String CLIENT_ID = 'beta-app';

// ======================
// I18N
// ======================
const List<String> supportedLanguages = [
  'de',
  'en',
  'it',
  'fr',
  'es',
  'nl',
  'pt',
  'cs',
  'pl',
];

const Map<String, Map<String, String>> localizedStrings = {
  'title': {
    'de': 'GrowDoctor Beta',
    'en': 'GrowDoctor Beta',
    'it': 'GrowDoctor Beta',
    'fr': 'GrowDoctor Bêta',
    'es': 'GrowDoctor Beta',
    'nl': 'GrowDoctor Beta',
    'pt': 'GrowDoctor Beta',
    'cs': 'GrowDoctor Beta',
    'pl': 'GrowDoctor Beta',
  },

  // Tabs
  'tab_diagnosis': {
    'de': 'Diagnose',
    'en': 'Diagnosis',
    'it': 'Diagnosi',
    'fr': 'Diagnostic',
    'es': 'Diagnóstico',
    'nl': 'Diagnose',
    'pt': 'Diagnóstico',
    'cs': 'Diagnostika',
    'pl': 'Diagnoza',
  },
  'tab_settings': {
    'de': 'Einstellungen',
    'en': 'Settings',
    'it': 'Impostazioni',
    'fr': 'Paramètres',
    'es': 'Ajustes',
    'nl': 'Instellingen',
    'pt': 'Configurações',
    'cs': 'Nastavení',
    'pl': 'Ustawienia',
  },


  // Labels (Backend v1)
  'main_problem': {
    'de': 'Hauptproblem',
    'en': 'Main problem',
    'it': 'Problema principale',
    'fr': 'Problème principal',
    'es': 'Problema principal',
    'nl': 'Hoofdprobleem',
    'pt': 'Problema principal',
    'cs': 'Hlavní problém',
    'pl': 'Główny problem',
  },
  'category': {
    'de': 'Kategorie',
    'en': 'Category',
    'it': 'Categoria',
    'fr': 'Catégorie',
    'es': 'Categoría',
    'nl': 'Categorie',
    'pt': 'Categoria',
    'cs': 'Kategorie',
    'pl': 'Kategoria',
  },
  'probability': {
    'de': 'Wahrscheinlichkeit',
    'en': 'Probability',
    'it': 'Probabilità',
    'fr': 'Probabilité',
    'es': 'Probabilidad',
    'nl': 'Waarschijnlijkheid',
    'pt': 'Probabilidade',
    'cs': 'Pravděpodobnost',
    'pl': 'Prawdopodobieństwo',
  },
  'details': {
    'de': 'Details',
    'en': 'Details',
    'it': 'Dettagli',
    'fr': 'Détails',
    'es': 'Detalles',
    'nl': 'Details',
    'pt': 'Detalhes',
    'cs': 'Podrobnosti',
    'pl': 'Szczegóły',
  },
  'description': {
    'de': 'Beschreibung',
    'en': 'Description',
    'it': 'Descrizione',
    'fr': 'Description',
    'es': 'Descripción',
    'nl': 'Beschrijving',
    'pt': 'Descrição',
    'cs': 'Popis',
    'pl': 'Opis',
  },
  'photo_quality': {
    'de': 'Bildqualität',
    'en': 'Photo quality',
    'it': 'Qualità foto',
    'fr': 'Qualité photo',
    'es': 'Calidad de foto',
    'nl': 'Fotokwaliteit',
    'pt': 'Qualidade da foto',
    'cs': 'Kvalita fotky',
    'pl': 'Jakość zdjęcia',
  },
  'affected_parts': {
    'de': 'Betroffene Teile',
    'en': 'Affected parts',
    'it': 'Parti colpite',
    'fr': 'Parties touchées',
    'es': 'Partes afectadas',
    'nl': 'Getroffen delen',
    'pt': 'Partes afetadas',
    'cs': 'Zasažené části',
    'pl': 'Dotknięte części',
  },
  'symptoms': {
    'de': 'Sichtbare Symptome',
    'en': 'Visible symptoms',
    'it': 'Sintomi visibili',
    'fr': 'Symptômes visibles',
    'es': 'Síntomas visibles',
    'nl': 'Zichtbare symptomen',
    'pt': 'Sintomas visíveis',
    'cs': 'Viditelné příznaky',
    'pl': 'Widoczne objawy',
  },
  'possible_causes': {
    'de': 'Mögliche Ursachen',
    'en': 'Possible causes',
    'it': 'Possibili cause',
    'fr': 'Causes possibles',
    'es': 'Causas posibles',
    'nl': 'Mogelijke oorzaken',
    'pt': 'Causas possíveis',
    'cs': 'Možné příčiny',
    'pl': 'Możliwe przyczyny',
  },
  'immediate_actions': {
    'de': 'Sofort-Maßnahmen',
    'en': 'Immediate actions',
    'it': 'Azioni immediate',
    'fr': 'Mesures immédiates',
    'es': 'Acciones inmediatas',
    'nl': 'Directe acties',
    'pt': 'Ações imediatas',
    'cs': 'Okamžité kroky',
    'pl': 'Działania natychmiastowe',
  },
  'prevention': {
    'de': 'Vorbeugung',
    'en': 'Prevention',
    'it': 'Prevenzione',
    'fr': 'Prévention',
    'es': 'Prevención',
    'nl': 'Preventie',
    'pt': 'Prevenção',
    'cs': 'Prevence',
    'pl': 'Zapobieganie',
  },
  'uncertain_hint': {
    'de': 'Hinweis: Ergebnis ist unsicher. Bitte Foto/Infos verbessern.',
    'en': 'Note: Result is uncertain. Improve photo/info.',
    'it': 'Nota: Risultato incerto. Migliora foto/info.',
    'fr': 'Note : Résultat incertain. Améliorez photo/infos.',
    'es': 'Nota: Resultado incierto. Mejora foto/info.',
    'nl': 'Let op: Resultaat onzeker. Verbeter foto/info.',
    'pt': 'Nota: Resultado incerto. Melhore foto/info.',
    'cs': 'Pozn.: Výsledek je nejistý. Zlepšete foto/info.',
    'pl': 'Uwaga: Wynik niepewny. Popraw zdjęcie/informacje.',
  },
  'photo_tips': {
    'de': 'Foto-Tipps',
    'en': 'Photo tips',
    'it': 'Consigli foto',
    'fr': 'Conseils photo',
    'es': 'Consejos de foto',
    'nl': 'Fototips',
    'pt': 'Dicas de foto',
    'cs': 'Tipy na fotku',
    'pl': 'Wskazówki do zdjęcia',
  },
  'photo_hint_low_quality': {
    'de': 'Die Bildqualität ist eher niedrig. Bitte mache ein schärferes, helleres Foto.',
    'en': 'Photo quality is low. Please take a sharper, brighter photo.',
    'it': 'Qualità foto bassa. Scatta una foto più nitida e luminosa.',
    'fr': 'Qualité photo faible. Prenez une photo plus nette et lumineuse.',
    'es': 'Calidad baja. Toma una foto más nítida y luminosa.',
    'nl': 'Fotokwaliteit laag. Maak een scherpere, heldere foto.',
    'pt': 'Qualidade baixa. Tire uma foto mais nítida e iluminada.',
    'cs': 'Nízká kvalita. Udělejte ostřejší a světlejší fotku.',
    'pl': 'Niska jakość. Zrób ostrzejsze i jaśniejsze zdjęcie.',
  },
  'photo_hint_uncertain': {
    'de': 'Für mehr Sicherheit: Lade zusätzlich Fotos von Oberseite, Unterseite und Gesamtsicht hoch.',
    'en': 'For more certainty: upload top, underside and whole-plant photos.',
    'it': 'Per più certezza: carica foto sopra, sotto e pianta intera.',
    'fr': 'Pour plus de certitude : ajoutez des photos dessus, dessous et plante entière.',
    'es': 'Para más certeza: sube fotos arriba, abajo y planta entera.',
    'nl': 'Voor meer zekerheid: upload bovenkant, onderkant en totaalbeeld.',
    'pt': 'Para mais certeza: envie fotos de cima, de baixo e da planta inteira.',
    'cs': 'Pro větší jistotu: nahrajte fotky shora, zespodu a celé rostliny.',
    'pl': 'Dla pewności: dodaj zdjęcia z góry, z dołu i całej rośliny.',
  },

  // Diagnose
  'diagnosis_title': {
    'de': 'Pflanzen-Diagnose',
    'en': 'Plant diagnosis',
    'it': 'Diagnosi pianta',
    'fr': 'Diagnostic plante',
    'es': 'Diagnóstico de plantas',
    'nl': 'Planten diagnose',
    'pt': 'Diagnóstico da planta',
    'cs': 'Diagnostika rostlin',
    'pl': 'Diagnoza rośliny',
  },
  'btn_gallery': {
    'de': 'Foto aus Galerie auswählen',
    'en': 'Select photo from gallery',
    'it': 'Seleziona dalla galleria',
    'fr': 'Choisir dans la galerie',
    'es': 'Elegir de la galería',
    'nl': 'Kies uit galerij',
    'pt': 'Escolher da galeria',
    'cs': 'Vybrat z galerie',
    'pl': 'Wybierz z galerii',
  },
  'btn_camera': {
    'de': 'Foto mit Kamera aufnehmen',
    'en': 'Take photo with camera',
    'it': 'Scatta una foto',
    'fr': 'Prendre une photo',
    'es': 'Tomar foto',
    'nl': 'Maak foto',
    'pt': 'Tirar foto',
    'cs': 'Vyfotit',
    'pl': 'Zrób zdjęcie',
  },

  // Foto Details
  'photo_details_title': {
    'de': 'Foto-Details (optional)',
    'en': 'Photo details (optional)',
    'it': 'Dettagli foto (opzionale)',
    'fr': 'Détails photo (optionnel)',
    'es': 'Detalles de foto (opcional)',
    'nl': 'Foto-details (optioneel)',
    'pt': 'Detalhes da foto (opcional)',
    'cs': 'Detaily fotky (volitelné)',
    'pl': 'Szczegóły zdjęcia (opcjonalne)',
  },
  'photo_position': {
    'de': 'Bildposition (Pflanze)',
    'en': 'Plant position',
    'it': 'Posizione sulla pianta',
    'fr': 'Position sur la plante',
    'es': 'Posición en la planta',
    'nl': 'Positie op plant',
    'pt': 'Posição na planta',
    'cs': 'Pozice na rostlině',
    'pl': 'Pozycja na roślinie',
  },
  'shot_type': {
    'de': 'Bildart / Foto-Typ',
    'en': 'Image type / Shot type',
    'it': 'Tipo immagine / Scatto',
    'fr': 'Type d’image / Prise',
    'es': 'Tipo de imagen / toma',
    'nl': 'Afbeeldingstype',
    'pt': 'Tipo de imagem',
    'cs': 'Typ snímku',
    'pl': 'Typ zdjęcia',
  },

  // Loading
  'analyzing': {
    'de': 'GrowDoctor analysiert…',
    'en': 'GrowDoctor is analyzing…',
    'it': 'GrowDoctor sta analizzando…',
    'fr': 'GrowDoctor analyse…',
    'es': 'GrowDoctor está analizando…',
    'nl': 'GrowDoctor analyseert…',
    'pt': 'GrowDoctor está analisando…',
    'cs': 'GrowDoctor analyzuje…',
    'pl': 'GrowDoctor analizuje…',
  },

  // Errors
  'error_server': {
    'de': 'Fehler vom Server',
    'en': 'Error from server',
    'it': 'Errore dal server',
    'fr': 'Erreur du serveur',
    'es': 'Error del servidor',
    'nl': 'Serverfout',
    'pt': 'Erro do servidor',
    'cs': 'Chyba serveru',
    'pl': 'Błąd serwera',
  },
  'error_connection': {
    'de': 'Verbindungsfehler oder Kamera-Fehler',
    'en': 'Connection or camera error',
    'it': 'Errore connessione o fotocamera',
    'fr': 'Erreur de connexion ou caméra',
    'es': 'Error de conexión o cámara',
    'nl': 'Verbindings- of camerafout',
    'pt': 'Erro de conexão ou câmera',
    'cs': 'Chyba připojení nebo kamery',
    'pl': 'Błąd połączenia lub aparatu',
  },
  'timeout_error': {
    'de': TIMEOUT_FALLBACK_DE,
    'en': 'The image needs a more precise analysis. Please upload it again.',
    'it': 'L’immagine richiede un’analisi più precisa. Caricala di nuovo.',
    'fr': 'L’image doit être analysée plus précisément. Veuillez la recharger.',
    'es': 'La imagen requiere un análisis más preciso. Vuelve a cargarla.',
    'nl': 'De foto vereist een nauwkeurigere analyse. Upload opnieuw.',
    'pt': 'A imagem precisa de uma análise mais precisa. Envie novamente.',
    'cs': 'Obrázek vyžaduje přesnější analýzu. Nahraj ho znovu.',
    'pl': 'Zdjęcie wymaga dokładniejszej analizy. Prześlij je ponownie.',
  },

  // Same image confirm
  'same_image_title': {
    'de': 'Gleiches Bild erkannt',
    'en': 'Same image detected',
    'it': 'Stessa immagine rilevata',
    'fr': 'Même image détectée',
    'es': 'Misma imagen detectada',
    'nl': 'Zelfde foto gedetecteerd',
    'pt': 'Mesma imagem detectada',
    'cs': 'Stejný obrázek',
    'pl': 'To samo zdjęcie',
  },
  'same_image_body': {
    'de': 'Dieses Bild wurde bereits analysiert. Trotzdem erneut analysieren?',
    'en': 'This image was already analyzed. Analyze again anyway?',
    'it': 'Questa immagine è già stata analizzata. Analizzare di nuovo?',
    'fr': 'Cette image a déjà été analysée. Analyser quand même ?',
    'es': 'Esta imagen ya fue analizada. ¿Analizar de nuevo?',
    'nl': 'Deze foto is al geanalyseerd. Toch opnieuw analyseren?',
    'pt': 'Esta imagem já foi analisada. Analisar novamente?',
    'cs': 'Tento obrázek už byl analyzován. Analyzovat znovu?',
    'pl': 'To zdjęcie było już analizowane. Analizować ponownie?',
  },
  'cancel': {
    'de': 'Abbrechen',
    'en': 'Cancel',
    'it': 'Annulla',
    'fr': 'Annuler',
    'es': 'Cancelar',
    'nl': 'Annuleren',
    'pt': 'Cancelar',
    'cs': 'Zrušit',
    'pl': 'Anuluj',
  },
  'analyze_anyway': {
    'de': 'Trotzdem analysieren',
    'en': 'Analyze anyway',
    'it': 'Analizza comunque',
    'fr': 'Analyser quand même',
    'es': 'Analizar de todos modos',
    'nl': 'Toch analyseren',
    'pt': 'Analisar mesmo assim',
    'cs': 'Přesto analyzovat',
    'pl': 'Analizuj mimo to',
  },

  // Age gate
  'age_title': {
    'de': 'Altersbestätigung',
    'en': 'Age verification',
    'it': 'Verifica età',
    'fr': 'Vérification d’âge',
    'es': 'Verificación de edad',
    'nl': 'Leeftijdscontrole',
    'pt': 'Verificação de idade',
    'cs': 'Ověření věku',
    'pl': 'Weryfikacja wieku',
  },
  'age_text_explicit': {
    'de': 'Ich bestätige, dass ich mindestens 18 Jahre alt bin.',
    'en': 'I confirm that I am at least 18 years old.',
    'it': 'Confermo di avere almeno 18 anni.',
    'fr': 'Je confirme avoir au moins 18 ans.',
    'es': 'Confirmo que tengo al menos 18 años.',
    'nl': 'Ik bevestig dat ik minstens 18 jaar oud ben.',
    'pt': 'Confirmo que tenho pelo menos 18 anos.',
    'cs': 'Potvrzuji, že mi je alespoň 18 let.',
    'pl': 'Potwierdzam, że mam co najmniej 18 lat.',
  },
  'confirm': {
    'de': 'Ich bestätige',
    'en': 'I confirm',
    'it': 'Confermo',
    'fr': 'Je confirme',
    'es': 'Confirmo',
    'nl': 'Ik bevestig',
    'pt': 'Confirmo',
    'cs': 'Potvrzuji',
    'pl': 'Potwierdzam',
  },
  'exit': {
    'de': 'Beenden',
    'en': 'Exit',
    'it': 'Esci',
    'fr': 'Quitter',
    'es': 'Salir',
    'nl': 'Afsluiten',
    'pt': 'Sair',
    'cs': 'Ukončit',
    'pl': 'Zamknij',
  },

  // Legal/disclaimer
  'legal_title': {
    'de': 'Wichtiger Hinweis (Haftungsausschluss)',
    'en': 'Important notice (Disclaimer)',
    'it': 'Avviso importante (Disclaimer)',
    'fr': 'Avis important (Clause de non-responsabilité)',
    'es': 'Aviso importante (Descargo)',
    'nl': 'Belangrijke melding (Disclaimer)',
    'pt': 'Aviso importante (Isenção)',
    'cs': 'Důležité upozornění (Prohlášení)',
    'pl': 'Ważna informacja (Zastrzeżenie)',
  },
  'legal_text': {
    'de':
        'GrowDoctor liefert eine KI-gestützte Bildanalyse als Orientierungshilfe.\n\n'
        '• Keine Garantie auf Richtigkeit/Vollständigkeit.\n'
        '• Keine medizinische Beratung.\n'
        '• Keine Anleitung zum Anbau oder Konsum.\n\n'
        'Bei starken Symptomen, rascher Verschlechterung oder Schimmelverdacht: '
        'Bitte einen erfahrenen Grower/Expert*in hinzuziehen.\n\n'
        'Mit „OK“ bestätigst du, dass du diesen Hinweis verstanden hast.',
    'en':
        'GrowDoctor provides an AI-based image analysis for orientation.\n\n'
        '• No guarantee of accuracy or completeness.\n'
        '• Not medical advice.\n'
        '• Not instructions for growing or consumption.\n\n'
        'If symptoms are severe, worsening fast, or mold is suspected: '
        'consult an experienced expert.\n\n'
        'By pressing “OK” you confirm you understand this notice.',
    'it':
        'GrowDoctor offre un’analisi immagini basata su IA come supporto.\n\n'
        '• Nessuna garanzia di correttezza/completezza.\n'
        '• Nessun consiglio medico.\n'
        '• Nessuna istruzione su coltivazione o consumo.\n\n'
        'In caso di sintomi gravi o sospetto muffa: consulta un esperto.\n\n'
        'Premendo “OK” confermi di aver compreso.',
    'fr':
        'GrowDoctor fournit une analyse d’images par IA à titre indicatif.\n\n'
        '• Aucune garantie d’exactitude/complétude.\n'
        '• Pas un avis médical.\n'
        '• Pas d’instructions de culture ou de consommation.\n\n'
        'En cas de symptômes sévères ou suspicion de moisissure : consultez un expert.\n\n'
        'En appuyant sur « OK », vous confirmez avoir compris.',
    'es':
        'GrowDoctor ofrece un análisis de imágenes con IA como orientación.\n\n'
        '• Sin garantía de precisión/completitud.\n'
        '• No es consejo médico.\n'
        '• No son instrucciones de cultivo o consumo.\n\n'
        'Si hay síntomas fuertes o sospecha de moho: consulta a un experto.\n\n'
        'Con “OK” confirmas que lo entiendes.',
    'nl':
        'GrowDoctor geeft een AI-beeldanalyse als hulpmiddel.\n\n'
        '• Geen garantie op juistheid/volledigheid.\n'
        '• Geen medisch advies.\n'
        '• Geen instructies voor teelt of consumptie.\n\n'
        'Bij ernstige symptomen of vermoeden van schimmel: raadpleeg een expert.\n\n'
        'Met “OK” bevestig je dat je dit begrijpt.',
    'pt':
        'GrowDoctor fornece uma análise de imagem por IA como orientação.\n\n'
        '• Sem garantia de precisão/completude.\n'
        '• Não é aconselhamento médico.\n'
        '• Não é instrução de cultivo ou consumo.\n\n'
        'Em caso de sintomas graves ou suspeita de mofo: consulte um especialista.\n\n'
        'Ao tocar “OK” você confirma que entendeu.',
    'cs':
        'GrowDoctor poskytuje analýzu obrázku pomocí AI pouze orientačně.\n\n'
        '• Bez záruky správnosti/úplnosti.\n'
        '• Nejde o lékařské doporučení.\n'
        '• Nejde o návod k pěstování nebo užívání.\n\n'
        'Při vážných příznacích nebo podezření na plíseň: kontaktujte odborníka.\n\n'
        'Stisknutím „OK“ potvrzujete, že jste upozornění pochopil/a.',
    'pl':
        'GrowDoctor dostarcza analizę obrazu AI jako wskazówkę.\n\n'
        '• Brak gwarancji poprawności/kompletności.\n'
        '• To nie jest porada medyczna.\n'
        '• To nie są instrukcje uprawy ani używania.\n\n'
        'Przy silnych objawach lub podejrzeniu pleśni: skonsultuj się z ekspertem.\n\n'
        'Naciskając „OK” potwierdzasz zrozumienie.',
  },
  'ok': {
    'de': 'OK',
    'en': 'OK',
    'it': 'OK',
    'fr': 'OK',
    'es': 'OK',
    'nl': 'OK',
    'pt': 'OK',
    'cs': 'OK',
    'pl': 'OK'
  },

  // Settings
  'settings_title': {
    'de': 'Einstellungen',
    'en': 'Settings',
    'it': 'Impostazioni',
    'fr': 'Paramètres',
    'es': 'Ajustes',
    'nl': 'Instellingen',
    'pt': 'Configurações',
    'cs': 'Nastavení',
    'pl': 'Ustawienia',
  },
  'settings_theme_title': {
    'de': 'Darstellung (Theme)',
    'en': 'Appearance (Theme)',
    'it': 'Aspetto (Tema)',
    'fr': 'Apparence (Thème)',
    'es': 'Apariencia (Tema)',
    'nl': 'Weergave (Thema)',
    'pt': 'Aparência (Tema)',
    'cs': 'Vzhled (Motiv)',
    'pl': 'Wygląd (Motyw)',
  },
  'settings_theme_dark': {
    'de': 'Dunkel',
    'en': 'Dark',
    'it': 'Scuro',
    'fr': 'Sombre',
    'es': 'Oscuro',
    'nl': 'Donker',
    'pt': 'Escuro',
    'cs': 'Tmavý',
    'pl': 'Ciemny'
  },
  'settings_theme_light': {
    'de': 'Hell',
    'en': 'Light',
    'it': 'Chiaro',
    'fr': 'Clair',
    'es': 'Claro',
    'nl': 'Licht',
    'pt': 'Claro',
    'cs': 'Světlý',
    'pl': 'Jasny'
  },

  'menu_legal': {
    'de': 'Hinweise',
    'en': 'Legal',
    'it': 'Note',
    'fr': 'Mentions',
    'es': 'Avisos',
    'nl': 'Info',
    'pt': 'Avisos',
    'cs': 'Info',
    'pl': 'Informacje'
  },
  'menu_privacy': {
    'de': 'Datenschutz',
    'en': 'Privacy',
    'it': 'Privacy',
    'fr': 'Confidentialité',
    'es': 'Privacidad',
    'nl': 'Privacy',
    'pt': 'Privacidade',
    'cs': 'Soukromí',
    'pl': 'Prywatność'
  },
  'menu_feedback': {
    'de': 'Feedback',
    'en': 'Feedback',
    'it': 'Feedback',
    'fr': 'Retour',
    'es': 'Feedback',
    'nl': 'Feedback',
    'pt': 'Feedback',
    'cs': 'Zpětná vazba',
    'pl': 'Opinia'
  },
  'menu_contact': {
    'de': 'Kontakt',
    'en': 'Contact',
    'it': 'Contatto',
    'fr': 'Contact',
    'es': 'Contacto',
    'nl': 'Contact',
    'pt': 'Contato',
    'cs': 'Kontakt',
    'pl': 'Kontakt'
  },

  'reset_age': {
    'de': 'Altersbestätigung zurücksetzen',
    'en': 'Reset age verification',
    'it': 'Reimposta verifica età',
    'fr': 'Réinitialiser la vérification d’âge',
    'es': 'Restablecer verificación de edad',
    'nl': 'Leeftijdscontrole resetten',
    'pt': 'Redefinir verificação de idade',
    'cs': 'Resetovat ověření věku',
    'pl': 'Zresetuj weryfikację wieku',
  },

  // Feedback UI
  'feedback_title': {
    'de': 'War diese Analyse hilfreich?',
    'en': 'Was this analysis helpful?',
    'it': 'Questa analisi è stata utile?',
    'fr': 'Cette analyse était-elle utile ?',
    'es': '¿Fue útil este análisis?',
    'nl': 'Was deze analyse nuttig?',
    'pt': 'Esta análise foi útil?',
    'cs': 'Byla tato analýza užitečná?',
    'pl': 'Czy ta analiza była pomocna?',
  },
  'feedback_hint': {
    'de': 'Optional: kurzer Kommentar (z.B. was gefehlt hat)',
    'en': 'Optional: short comment (e.g. what was missing)',
    'it': 'Opzionale: breve commento (es. cosa mancava)',
    'fr': 'Optionnel : court commentaire (ex. ce qui manquait)',
    'es': 'Opcional: comentario breve (p.ej. qué faltó)',
    'nl': 'Optioneel: korte opmerking (bv. wat miste)',
    'pt': 'Opcional: comentário curto (ex. o que faltou)',
    'cs': 'Volitelné: krátký komentář (co chybělo)',
    'pl': 'Opcjonalnie: krótki komentarz (czego brakowało)',
  },
  'send': {
    'de': 'Senden',
    'en': 'Send',
    'it': 'Invia',
    'fr': 'Envoyer',
    'es': 'Enviar',
    'nl': 'Versturen',
    'pt': 'Enviar',
    'cs': 'Odeslat',
    'pl': 'Wyślij',
  },
  'thanks': {
    'de': 'Danke für dein Feedback!',
    'en': 'Thanks for your feedback!',
    'it': 'Grazie per il feedback!',
    'fr': 'Merci pour votre retour !',
    'es': '¡Gracias por tu feedback!',
    'nl': 'Bedankt voor je feedback!',
    'pt': 'Obrigado pelo feedback!',
    'cs': 'Děkujeme za zpětnou vazbu!',
    'pl': 'Dziękujemy za opinię!',
  },
};

class GrowDoctorBetaApp extends StatefulWidget {
  const GrowDoctorBetaApp({super.key});

  @override
  State<GrowDoctorBetaApp> createState() => _GrowDoctorBetaAppState();
}

class _GrowDoctorBetaAppState extends State<GrowDoctorBetaApp> {
  ThemeMode _themeMode = ThemeMode.dark;

  @override
  Widget build(BuildContext context) {
    final ThemeData darkTheme = ThemeData(
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.green,
        brightness: Brightness.dark,
      ),
      scaffoldBackgroundColor: const Color(0xFF0E1712),
      cardColor: const Color(0xFF162118),
      useMaterial3: true,
    );

    final ThemeData lightTheme = ThemeData(
      brightness: Brightness.light,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.green,
        brightness: Brightness.light,
      ),
      scaffoldBackgroundColor: const Color(0xFFF5FFF4),
      cardColor: const Color(0xFFE3F2E1),
      useMaterial3: true,
    );

    return MaterialApp(
      title: APP_TITLE,
      debugShowCheckedModeBanner: false,
      theme: lightTheme,
      darkTheme: darkTheme,
      themeMode: _themeMode,
      home: BetaHomePage(
        themeMode: _themeMode,
        onThemeChanged: (mode) => setState(() => _themeMode = mode),
      ),
    );
  }
}

class BetaHomePage extends StatefulWidget {
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onThemeChanged;

  const BetaHomePage({
    super.key,
    required this.themeMode,
    required this.onThemeChanged,
  });

  @override
  State<BetaHomePage> createState() => _BetaHomePageState();
}

class _BetaHomePageState extends State<BetaHomePage> {
  // App State
  String _languageCode = 'de';

  // Foto-Details (werden immer gesendet)
  String _photoPosition = 'middle'; // top/middle/bottom/unknown
  String _shotType = 'whole'; // whole|detail|zoom|unknown

  // Diagnose
  Map<String, dynamic>? _diagnosis;
  bool _isLoading = false;
  String? _errorMessage;
  String? _infoMessage;

  Uint8List? _lastImageBytes;
  String? _lastImageSignature;

  // Gates
  bool _ageConfirmed = false;
  bool _legalConfirmed = false;

  // Feedback
  bool? _feedbackThumbUp; // true=up, false=down, null=not chosen yet
  final TextEditingController _feedbackController = TextEditingController();

  String t(String key) {
    final entry = localizedStrings[key];
    if (entry == null) return key;
    return entry[_languageCode] ?? entry['en'] ?? key;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _showAgeGateIfNeeded();
      await _showLegalIfNeeded();
      await _warmupBackend();
    });
  }

  @override
  void dispose() {
    _feedbackController.dispose();
    super.dispose();
  }

  Future<void> _warmupBackend() async {
    try {
      await http.get(Uri.parse('$BASE_URL/')).timeout(const Duration(seconds: 10));
    } catch (_) {
      // ignore
    }
  }

  // --------------------------
  // Store-safe Tracking (optional)
  // --------------------------
  Future<void> _track(String event, {Map<String, dynamic>? extra}) async {
    try {
      final uri = Uri.parse('$BASE_URL$METRICS_PATH');
      final payload = <String, dynamic>{
        'client_id': CLIENT_ID,
        'event': event,
        'lang': _languageCode,
        'ts': DateTime.now().toUtc().toIso8601String(),
        if (extra != null) 'extra': extra,
      };
      await http
          .post(uri, headers: {'Content-Type': 'application/json'}, body: jsonEncode(payload))
          .timeout(const Duration(seconds: 5));
    } catch (_) {
      // ignore
    }
  }

  // --------------------------
  // Age Gate (nicht umgehbar)
  // --------------------------
  Future<void> _showAgeGateIfNeeded() async {
    if (_ageConfirmed) return;

    final bool? ok = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => WillPopScope(
        onWillPop: () async => false,
        child: AlertDialog(
          title: Text(t('age_title')),
          content: Text(t('age_text_explicit')),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(t('exit')),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(t('confirm')),
            ),
          ],
        ),
      ),
    );

    if (ok == true) {
      setState(() => _ageConfirmed = true);
      await _track('age_confirmed');
    } else {
      setState(() {
        _ageConfirmed = false;
        _errorMessage = '18+ erforderlich.';
      });
      await _track('age_declined');
    }
  }

  // --------------------------
  // Legal Gate (nicht umgehbar)
  // --------------------------
  Future<void> _showLegalIfNeeded() async {
    if (_legalConfirmed) return;

    final bool? ok = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => WillPopScope(
        onWillPop: () async => false,
        child: AlertDialog(
          title: Text(t('legal_title')),
          content: SingleChildScrollView(child: Text(t('legal_text'))),
          actions: [
            ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(t('ok')),
            ),
          ],
        ),
      ),
    );

    if (ok == true) {
      setState(() => _legalConfirmed = true);
      await _track('legal_confirmed');
    }
  }

  // ---------- Helpers ----------
  MediaType _guessMediaType(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return MediaType('image', 'png');
    if (lower.endsWith('.webp')) return MediaType('image', 'webp');
    return MediaType('image', 'jpeg');
  }

  String _signatureForBytes(Uint8List bytes) {
    final slice = bytes.length > 2500 ? bytes.sublist(0, 2500) : bytes;
    return base64Encode(slice);
  }

  Future<bool> _confirmSameImage() async {
    final bool? ok = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: Text(t('same_image_title')),
        content: Text(t('same_image_body')),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(t('cancel')),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(t('analyze_anyway')),
          ),
        ],
      ),
    );
    return ok == true;
  }

  // ---------- Diagnose ----------
  Future<void> _pickAndDiagnose(ImageSource source) async {
    if (!_ageConfirmed) {
      await _showAgeGateIfNeeded();
      if (!_ageConfirmed) return;
    }
    if (!_legalConfirmed) {
      await _showLegalIfNeeded();
      if (!_legalConfirmed) return;
    }

    setState(() {
      _errorMessage = null;
      _infoMessage = null;
    });

    final picker = ImagePicker();

    try {
      final XFile? file = await picker.pickImage(source: source, imageQuality: 85);
      if (file == null) return;

      final bytes = await file.readAsBytes();
      final signature = _signatureForBytes(bytes);
      final bool isSame = (_lastImageSignature != null && _lastImageSignature == signature);

      bool force = false;
      if (isSame) {
        final ok = await _confirmSameImage();
        if (!ok) return;
        force = true;
      }

      setState(() {
        _isLoading = true;
        _diagnosis = null;
        _feedbackThumbUp = null;
        _feedbackController.clear();
        _lastImageBytes = bytes;
        _lastImageSignature = signature;
      });

      await _track('diagnose_start', extra: {
        'source': source == ImageSource.camera ? 'camera' : 'gallery',
        'photo_position': _photoPosition,
        'shot_type': _shotType,
        'force': force,
      });

      final uri = Uri.parse('$BASE_URL$DIAGNOSE_PATH');
      final request = http.MultipartRequest('POST', uri);

      request.fields['age_confirmed'] = 'true';
      request.fields['lang'] = _languageCode;
      request.fields['photo_position'] = _photoPosition;
      request.fields['shot_type'] = _shotType;
      request.fields['client_id'] = CLIENT_ID;
      request.fields['force'] = force ? 'true' : 'false';

      request.files.add(
        http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: file.name,
          contentType: _guessMediaType(file.name),
        ),
      );

      final streamed = await request.send().timeout(REQUEST_TIMEOUT);
      final body = await streamed.stream.bytesToString().timeout(REQUEST_TIMEOUT);

      if (streamed.statusCode >= 200 && streamed.statusCode < 300) {
        final Map<String, dynamic> data = json.decode(body) as Map<String, dynamic>;
        setState(() => _diagnosis = data);
        await _track('diagnose_success');
      } else {
        setState(() {
          _errorMessage =
              '${t('error_server')} (${streamed.statusCode}): ${body.isNotEmpty ? body : 'Unknown error'}';
        });
        await _track('diagnose_error', extra: {'status': streamed.statusCode});
      }
    } on TimeoutException {
      setState(() => _errorMessage = t('timeout_error'));
      await _track('diagnose_timeout');
    } catch (e) {
      setState(() => _errorMessage = '${t('error_connection')}: $e');
      await _track('diagnose_exception', extra: {'msg': e.toString()});
    } finally {
      setState(() => _isLoading = false);
    }
  }

  // ---------- Feedback ----------
  Future<void> _sendFeedback() async {
    if (_diagnosis == null) return;
    if (_feedbackThumbUp == null) return;

    final payload = <String, dynamic>{
      'client_id': CLIENT_ID,
      'thumb': _feedbackThumbUp == true ? 'up' : 'down',
      'comment': _feedbackController.text.trim(),
      'ts': DateTime.now().toUtc().toIso8601String(),
      'photo_position': _photoPosition,
      'shot_type': _shotType,
    };

    await _track('feedback_submit', extra: payload);

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(t('thanks'))),
    );

    setState(() {
      _feedbackThumbUp = null;
      _feedbackController.clear();
    });
  }

  // ---------- UI ----------
  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(t('title')),
          actions: [
            PopupMenuButton<String>(
              icon: const Icon(Icons.language),
              onSelected: (value) => setState(() => _languageCode = value),
              itemBuilder: (context) => supportedLanguages
                  .map((l) => PopupMenuItem(value: l, child: Text(l.toUpperCase())))
                  .toList(),
            ),
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert),
              onSelected: (value) {
                if (value == 'legal') {
                  _openInfoPage(t('menu_legal'), t('legal_text'));
                } else if (value == 'privacy') {
                  _openInfoPage(t('menu_privacy'), _privacyText());
                } else if (value == 'feedback') {
                  _openInfoPage(t('menu_feedback'), _feedbackText());
                } else if (value == 'contact') {
                  _openInfoPage(t('menu_contact'), _contactText());
                }
              },
              itemBuilder: (context) => [
                PopupMenuItem(value: 'legal', child: Text(t('menu_legal'))),
                PopupMenuItem(value: 'privacy', child: Text(t('menu_privacy'))),
                PopupMenuItem(value: 'feedback', child: Text(t('menu_feedback'))),
                PopupMenuItem(value: 'contact', child: Text(t('menu_contact'))),
              ],
            ),
          ],
          bottom: TabBar(
            tabs: [
              Tab(text: t('tab_diagnosis')),
              Tab(text: t('tab_settings')),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _buildDiagnosisTab(),
            _buildSettingsTab(),
          ],
        ),
      ),
    );
  }

  Widget _buildDiagnosisTab() {
    final diagnosis = _diagnosis;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: ListView(
        children: [
          Text(
            t('diagnosis_title'),
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),

          Card(
            child: ExpansionTile(
              title: Text(
                t('photo_details_title'),
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              subtitle: Text(
                'Position: $_photoPosition • Typ: $_shotType',
                style: const TextStyle(fontSize: 12),
              ),
              childrenPadding: const EdgeInsets.all(12),
              children: [
                DropdownButtonFormField<String>(
                  value: _photoPosition,
                  decoration: InputDecoration(
                    labelText: t('photo_position'),
                    border: const OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: 'top', child: Text('Oben (Top)')),
                    DropdownMenuItem(value: 'middle', child: Text('Mitte')),
                    DropdownMenuItem(value: 'bottom', child: Text('Unten')),
                    DropdownMenuItem(value: 'unknown', child: Text('Unbekannt')),
                  ],
                  onChanged: (v) {
                    if (v == null) return;
                    setState(() => _photoPosition = v);
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: _shotType,
                  decoration: InputDecoration(
                    labelText: t('shot_type'),
                    border: const OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: 'whole', child: Text('Ganze Pflanze')),
                    DropdownMenuItem(value: 'detail', child: Text('Detail (Blatt/Stelle)')),
                    DropdownMenuItem(value: 'zoom', child: Text('Makro/Zoom')),
                    DropdownMenuItem(value: 'unknown', child: Text('Unbekannt')),
                  ],
                  onChanged: (v) {
                    if (v == null) return;
                    setState(() => _shotType = v);
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          ElevatedButton.icon(
            onPressed: _isLoading ? null : () => _pickAndDiagnose(ImageSource.gallery),
            icon: const Icon(Icons.photo_library),
            label: Text(t('btn_gallery')),
          ),
          const SizedBox(height: 8),

          ElevatedButton.icon(
            onPressed: _isLoading ? null : () => _pickAndDiagnose(ImageSource.camera),
            icon: const Icon(Icons.camera_alt),
            label: Text(t('btn_camera')),
          ),

          const SizedBox(height: 12),

          if (_lastImageBytes != null) ...[
            Card(
              elevation: 3,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Image.memory(_lastImageBytes!, fit: BoxFit.cover),
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],

          if (_infoMessage != null) ...[
            Text(_infoMessage!, style: const TextStyle(color: Colors.amber)),
            const SizedBox(height: 8),
          ],

          if (_errorMessage != null) ...[
            Text(_errorMessage!, style: const TextStyle(color: Colors.redAccent)),
            const SizedBox(height: 12),
          ],

          if (_isLoading) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                const SizedBox(width: 8),
                const CircularProgressIndicator(),
                const SizedBox(width: 14),
                Expanded(child: Text(t('analyzing'))),
              ],
            ),
            const SizedBox(height: 16),
          ],

          if (diagnosis != null) ...[
            _DiagnosisSummaryCard(diagnosis: diagnosis),
            const SizedBox(height: 16),
            _DetailsSection(diagnosis: diagnosis),
            const SizedBox(height: 16),
            _PhotoHintsSection(diagnosis: diagnosis),
            const SizedBox(height: 16),
            _FeedbackCard(
              title: t('feedback_title'),
              hint: t('feedback_hint'),
              thumb: _feedbackThumbUp,
              controller: _feedbackController,
              onThumbUp: () => setState(() => _feedbackThumbUp = true),
              onThumbDown: () => setState(() => _feedbackThumbUp = false),
              onSend: _sendFeedback,
              sendLabel: t('send'),
            ),
          ],

          const SizedBox(height: 12),
        ],
      ),
    );
  }

  Widget _buildSettingsTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: ListView(
        children: [
          Text(
            t('settings_title'),
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),

          Text(t('settings_theme_title'), style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          RadioListTile<ThemeMode>(
            title: Text(t('settings_theme_dark')),
            value: ThemeMode.dark,
            groupValue: widget.themeMode,
            onChanged: (mode) {
              if (mode != null) widget.onThemeChanged(mode);
            },
          ),
          RadioListTile<ThemeMode>(
            title: Text(t('settings_theme_light')),
            value: ThemeMode.light,
            groupValue: widget.themeMode,
            onChanged: (mode) {
              if (mode != null) widget.onThemeChanged(mode);
            },
          ),

          const SizedBox(height: 16),
          const Card(
            child: ListTile(
              leading: Icon(Icons.cloud_outlined),
              title: Text('Backend'),
              subtitle: Text('Verbunden'),
            ),
          ),

          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.lock_reset),
              title: Text(t('reset_age')),
              subtitle: const Text('Reset Age Confirmation'),
              onTap: () async {
                setState(() {
                  _ageConfirmed = false;
                  _legalConfirmed = false;
                  _diagnosis = null;
                  _errorMessage = null;
                  _infoMessage = null;
                  _feedbackThumbUp = null;
                  _feedbackController.clear();
                });
                await _track('age_reset');

                if (mounted) {
                  await _showAgeGateIfNeeded();
                  if (_ageConfirmed) {
                    await _showLegalIfNeeded();
                  }
                }
              },
            ),
          ),

          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.gavel_outlined),
              title: Text(t('menu_legal')),
              subtitle: Text(t('legal_title')),
              onTap: () => _openInfoPage(t('menu_legal'), t('legal_text')),
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.privacy_tip_outlined),
              title: Text(t('menu_privacy')),
              subtitle: const Text('Kurzfassung'),
              onTap: () => _openInfoPage(t('menu_privacy'), _privacyText()),
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.feedback_outlined),
              title: Text(t('menu_feedback')),
              subtitle: const Text('Support / Bugs / Vorschläge'),
              onTap: () => _openInfoPage(t('menu_feedback'), _feedbackText()),
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.email_outlined),
              title: Text(t('menu_contact')),
              subtitle: Text(SUPPORT_EMAIL),
              onTap: () => _openInfoPage(t('menu_contact'), _contactText()),
            ),
          ),
        ],
      ),
    );
  }

  // ---------- In-app info pages ----------
  void _openInfoPage(String title, String body) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _InfoPage(title: title, body: body),
      ),
    );
  }

  String _contactText() {
    return 'Kontakt:\n\n'
        'E-Mail: $SUPPORT_EMAIL\n\n'
        'Hinweis: Bitte sende keine sensiblen persönlichen Daten.\n';
  }

  String _feedbackText() {
    return 'Feedback:\n\n'
        'Bitte sende Feedback, Bugs und Verbesserungsvorschläge an:\n'
        '$SUPPORT_EMAIL\n\n'
        'Idealerweise mit:\n'
        '• Screenshot\n'
        '• was du erwartet hast\n'
        '• was passiert ist\n'
        '• Gerät/Android Version\n';
  }

  String _privacyText() {
    return 'Datenschutz (Kurzfassung):\n\n'
        '• Für die Analyse wird das ausgewählte Foto an den GrowDoctor-Server gesendet.\n'
        '• Es werden keine Konten/Logins benötigt.\n'
        '• Bitte keine Gesichter oder personenbezogene Informationen im Bild zeigen.\n'
        '• Wir speichern in der Beta keine personenbezogenen Daten.\n'
        '• Optional werden anonyme Nutzungsereignisse (z.B. Analyse gestartet/erfolgreich) an $METRICS_PATH übertragen.\n\n'
        'Kontakt Datenschutz: $SUPPORT_EMAIL\n';
  }
}

// ---------- UI Components ----------
class _InfoPage extends StatelessWidget {
  final String title;
  final String body;

  const _InfoPage({required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(APP_TITLE)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: SingleChildScrollView(child: Text(body)),
      ),
    );
  }
}

class _FeedbackCard extends StatelessWidget {
  final String title;
  final String hint;
  final bool? thumb;
  final TextEditingController controller;
  final VoidCallback onThumbUp;
  final VoidCallback onThumbDown;
  final VoidCallback onSend;
  final String sendLabel;

  const _FeedbackCard({
    required this.title,
    required this.hint,
    required this.thumb,
    required this.controller,
    required this.onThumbUp,
    required this.onThumbDown,
    required this.onSend,
    required this.sendLabel,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = thumb != null;

    return Card(
      elevation: 3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          Row(
            children: [
              IconButton(
                tooltip: '👍',
                onPressed: onThumbUp,
                icon: Icon(Icons.thumb_up, color: thumb == true ? Colors.greenAccent : null),
              ),
              IconButton(
                tooltip: '👎',
                onPressed: onThumbDown,
                icon: Icon(Icons.thumb_down, color: thumb == false ? Colors.redAccent : null),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  enabled ? '' : 'Bitte 👍 oder 👎 auswählen',
                  style: TextStyle(color: enabled ? null : Colors.amber),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: controller,
            maxLines: 3,
            decoration: InputDecoration(
              hintText: hint,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerRight,
            child: ElevatedButton.icon(
              onPressed: enabled ? onSend : null,
              icon: const Icon(Icons.send),
              label: Text(sendLabel),
            ),
          ),
        ]),
      ),
    );
  }
}


class _DiagnosisSummaryCard extends StatelessWidget {
  final Map<String, dynamic> diagnosis;
  const _DiagnosisSummaryCard({required this.diagnosis});

  int _toPercent(dynamic v) {
    if (v == null) return 0;
    final parsed = double.tryParse(v.toString());
    if (parsed == null) return 0;
    final p = (parsed <= 1.0) ? (parsed * 100.0) : parsed;
    return p.round().clamp(0, 100);
  }

  Map<String, dynamic> _result(Map<String, dynamic> d) {
    if (d['result'] is Map<String, dynamic>) return d['result'] as Map<String, dynamic>;
    return d;
  }

  String _ampelFrom(int probability, bool isUnsicher) {
    // Ampel zeigt hier primär die Diagnose-Sicherheit/Verlässlichkeit
    if (isUnsicher) return 'gelb';
    if (probability >= 70) return 'gruen';
    if (probability >= 40) return 'gelb';
    return 'rot';
  }

  Color _ampelColor(String a) {
    switch (a) {
      case 'gruen':
      case 'green':
        return Colors.green;
      case 'rot':
      case 'red':
        return Colors.redAccent;
      default:
        return Colors.amber;
    }
  }

  @override
  Widget build(BuildContext context) {
    final res = _result(diagnosis);

    final String main = (res['hauptproblem'] ?? res['problem'] ?? '-').toString();
    final String cat = (res['kategorie'] ?? '-').toString();
    final int p = _toPercent(res['wahrscheinlichkeit']);
    final bool isUnsicher = res['ist_unsicher'] == true;

    final String ampel = _ampelFrom(p, isUnsicher);
    final Color c = _ampelColor(ampel);

    return Card(
      elevation: 3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(
            children: [
              Container(
                width: 14,
                height: 14,
                decoration: BoxDecoration(color: c, shape: BoxShape.circle),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  main,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: Text('${t('category')}: $cat')),
              const SizedBox(width: 12),
              Text('${t('probability')}: $p%'),
            ],
          ),
          if (isUnsicher) ...[
            const SizedBox(height: 8),
            Text(
              t('uncertain_hint'),
              style: const TextStyle(color: Colors.black54),
            ),
          ],
        ]),
      ),
    );
  }
}



class _DetailsSection extends StatelessWidget {
  final Map<String, dynamic> diagnosis;
  const _DetailsSection({required this.diagnosis});

  Map<String, dynamic> _result(Map<String, dynamic> d) {
    if (d['result'] is Map<String, dynamic>) return d['result'] as Map<String, dynamic>;
    return d;
  }

  List<String> _list(dynamic v) {
    if (v is List) {
      return v.map((e) => e.toString()).where((s) => s.trim().isNotEmpty).toList();
    }
    if (v is String && v.trim().isNotEmpty) return [v.trim()];
    return <String>[];
  }

  String _bullet(List<String> items) => items.isEmpty ? '-' : '• ${items.join('
• ')}';

  @override
  Widget build(BuildContext context) {
    final res = _result(diagnosis);

    final String beschreibung = (res['beschreibung'] ?? '').toString().trim();
    final String qualHint = (res['hinweis_bildqualitaet'] ?? '').toString().trim();
    final int qualScore = int.tryParse((res['bildqualitaet_score'] ?? 0).toString())?.clamp(0, 100) ?? 0;

    final betroffene = _list(res['betroffene_teile']);
    final symptome = _list(res['sichtbare_symptome']);
    final ursachen = _list(res['moegliche_ursachen']);
    final massnahmen = _list(res['sofort_massnahmen']);
    final vorbeugung = _list(res['vorbeugung']);

    final Map<String, dynamic> legal =
        (diagnosis['legal'] is Map<String, dynamic>) ? diagnosis['legal'] as Map<String, dynamic> : {};

    final String disclaimerTitle = (legal['disclaimer_title'] ?? '').toString().trim();
    final String disclaimerBody = (legal['disclaimer_body'] ?? '').toString().trim();
    final String privacyTitle = (legal['privacy_title'] ?? '').toString().trim();
    final String privacyBody = (legal['privacy_body'] ?? '').toString().trim();

    return Card(
      elevation: 3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t('details'), style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),

          if (beschreibung.isNotEmpty) ...[
            Text(t('description'), style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(beschreibung),
            const SizedBox(height: 10),
          ],

          Text('${t('photo_quality')}: $qualScore/100'),
          if (qualHint.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(qualHint, style: const TextStyle(color: Colors.black54)),
          ],
          const SizedBox(height: 10),

          Text(t('affected_parts'), style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(_bullet(betroffene)),
          const SizedBox(height: 10),

          Text(t('symptoms'), style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(_bullet(symptome)),
          const SizedBox(height: 10),

          Text(t('possible_causes'), style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(_bullet(ursachen)),
          const SizedBox(height: 10),

          Text(t('immediate_actions'), style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(_bullet(massnahmen)),
          const SizedBox(height: 10),

          Text(t('prevention'), style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(_bullet(vorbeugung)),

          if (disclaimerTitle.isNotEmpty || disclaimerBody.isNotEmpty || privacyTitle.isNotEmpty || privacyBody.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Divider(),
            if (disclaimerTitle.isNotEmpty) Text(disclaimerTitle, style: const TextStyle(fontWeight: FontWeight.w600)),
            if (disclaimerBody.isNotEmpty) Text(disclaimerBody, style: const TextStyle(fontSize: 12, color: Colors.black54)),
            if (privacyTitle.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(privacyTitle, style: const TextStyle(fontWeight: FontWeight.w600)),
            ],
            if (privacyBody.isNotEmpty) Text(privacyBody, style: const TextStyle(fontSize: 12, color: Colors.black54)),
          ],
        ]),
      ),
    );
  }
}



class _PhotoHintsSection extends StatelessWidget {
  final Map<String, dynamic> diagnosis;
  const _PhotoHintsSection({required this.diagnosis});

  Map<String, dynamic> _result(Map<String, dynamic> d) {
    if (d['result'] is Map<String, dynamic>) return d['result'] as Map<String, dynamic>;
    return d;
  }

  @override
  Widget build(BuildContext context) {
    final res = _result(diagnosis);
    final int qualScore = int.tryParse((res['bildqualitaet_score'] ?? 0).toString())?.clamp(0, 100) ?? 0;
    final String qualHint = (res['hinweis_bildqualitaet'] ?? '').toString().trim();
    final bool isUnsicher = res['ist_unsicher'] == true;

    final List<Widget> hints = [];

    if (qualScore > 0 && qualScore < 60) {
      hints.add(Text(t('photo_hint_low_quality'), style: const TextStyle(color: Colors.black87)));
    }
    if (qualHint.isNotEmpty) {
      hints.add(Text(qualHint, style: const TextStyle(color: Colors.black54)));
    }
    if (isUnsicher) {
      hints.add(Text(t('photo_hint_uncertain'), style: const TextStyle(color: Colors.black87)));
    }

    if (hints.isEmpty) return const SizedBox.shrink();

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t('photo_tips'), style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          ...hints.map((w) => Padding(padding: const EdgeInsets.only(bottom: 6), child: w)),
        ]),
      ),
    );
  }
}

