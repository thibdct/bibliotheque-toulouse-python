# -*- coding: utf-8 -*-
"""
Fonctionnalité permettant de faire les requêtes HTTP vers le serveur du catalogue des bibliothèques de Toulouse <http://catalogues.toulouse.fr>
"""

import requests
from bs4 import BeautifulSoup
from urlparse import urljoin
import json

_URL_BASE="http://catalogues.toulouse.fr/web2/tramp2.exe/"
_URL_PAGE_ACCUEIL=urljoin(_URL_BASE,"log_in?setting_key=BMT1")
_URL_RECHERCHE=urljoin(_URL_BASE,"do_keyword_search/log_in?setting_key=BMT1&servers=1home&screen=hitlist.html&query=")
_TIMEOUT=30
_TITRE_PAGE_UN_RESULTAT=u"Notice détaillée Web2"
_TITRE_PAGE_PLUSIEURS_RESULTATS=u"Résultats de recherche"
_DEFAULT_BEAUTIFULSOUP_PARSER="lxml"

JAI_UNE_SESSION = False # = True quand on s'est au moins connecté une fois à l'accueil de la bibliothèque
URL_RECHERCHE = "" # Tant qu'on n'a pas de session, on n'a pas l'url de recherche
ID_SESSION = ""
    
class Client(object):
    """Fait les requêtes avec le serveur du catalogue des bibliothèques de Toulouse"""
    
    def __init__(self):
        """ Initialisation du client """
    
        self.session = requests.session()
        
    def _get(self, url):
        return self.session.get(url).text
    
    def _construire_url_recherche(self, titre, auteur):
        requete = ""
        if (titre != ""):
            requete = u"TI %s" % (titre)
            if (auteur != "") : requete += u" ET AU %s" % (auteur)
        elif (auteur != "") : requete = u"AU %s" % (auteur)
        requete=requete.strip()
        return (_URL_RECHERCHE+requete)
    
    def _css_selector(self, soup, css_selector="html"):
        """ Retourne une liste d'éléments à partir d'un sélecteur CSS passé en paramètre """
        # Dans Chrome, clic-droit sur un élément > Inspecter; puis dans le code source, clic-droit sur l'élément > Copy CSS path
        # _css_selector(soup, "title") # get title tag
        # _css_selector(soup, "body > a") # all a tag inside body
        # _css_selector(soup, ".sister") # select by class
        # _css_selector(soup, "#link1") # select by id
        # _css_selector(soup, 'a[href="http://example.com/elsie"]') # find tags by attribute value
        # _css_selector(soup, 'a[href^="http://example.com/"]') # find tags by attribute value, all contains 'http://example.com/'
        
        elements = []
        try :
            elements = soup.select(css_selector)
        except:
            print("ERROR : exception dans _css_selector") #TODO : Ajouter une exception
        return elements
    
    def _normaliser_auteur(self, auteur_brut):
        auteur=self._normaliser_chaine(auteur_brut)
        if len(auteur.split(',')) == 2 :
            nom, prenom = auteur.split(',')
            auteur = "%s %s" % (prenom.strip(), nom.strip())
        return auteur
    
    def _normaliser_titre(self, titre_brut):
        titre=self._normaliser_chaine(titre_brut)
        if titre[-1] == '/' : titre = titre[:-1] # Les titres finissent souvent par '/', ex : "Le meilleur des mondes /"
        titre = titre.strip()
        return titre
            
    def _extraire_infos_page_detaillee(self, soup="", page_html_detaillee="", url=""):
        """ Extrait les infos de la page détaillée d'une oeuvre, via le résultat de beautifulsoup,
        via le code source de la page, ou via l'URL """
        
        dict_infos = {}
        
        if (soup == ""):
            if (page_html_detaillee == "") : page_html_detaillee = self._get(url)
            soup = BeautifulSoup(page_html_detaillee, _DEFAULT_BEAUTIFULSOUP_PARSER)
            
        auteur_brut = self._css_selector(soup, 'div[id="auteur"] > a')[0].text.strip()
        auteur = self._normaliser_auteur(auteur_brut)
        titre_brut = self._css_selector(soup, 'td[width="95%"] > h1')[0].text.strip()
        titre = self._normaliser_titre(titre_brut)
        
        url_permanent = self._css_selector(soup, '#BW_link > input')
        if len(url_permanent) > 0 : url_permanent=url_permanent[0]["value"].strip()
        else : url_permanent=""
        
        isbn = self._css_selector(soup, '#isbn_livre')
        if len(isbn) > 0 : isbn=isbn[0].text.strip()
        else : isbn=""
        
        tableau_exemplaires = self._css_selector(soup, '#exemplaire_table > tr')
        liste_exemplaires = []
        for ligne in tableau_exemplaires:
            cellules = self._css_selector(ligne, 'td.holdingslistbab')
            if len(cellules) == 5: # Les lignes intéressantes contiennent 5 cellules
                dict_exemplaire = { u'bibliotheque'  : self._normaliser_chaine(cellules[0].text),
                                    u'cote'          : self._normaliser_chaine(cellules[1].text),
                                    u'materiel'      : self._normaliser_chaine(cellules[2].text),
                                    u'localisation'  : self._normaliser_chaine(cellules[3].text),
                                    u'retour_attendu': self._normaliser_chaine(cellules[4].text)
                                 }
                non_dispo = {u"Prêté", u"Document indisponible, acheminement en cours", u"Réservé"}

                if (dict_exemplaire[u'localisation'] in non_dispo) or (dict_exemplaire[u'materiel'] == ""):
                    dict_exemplaire[u'dispo'] = False
                else : dict_exemplaire[u'dispo'] = True
                
                liste_exemplaires.append(dict_exemplaire)
                
        dict_infos[u'titre'] = titre
        dict_infos[u'auteur'] = auteur
        dict_infos[u'url_permanent'] = url_permanent
        dict_infos[u'isbn'] = isbn
        dict_infos[u'exemplaires'] = liste_exemplaires
        
        return dict_infos
    
    def _extraire_infos_page_plusieurs_resultats(self, soup="", page_html_detaillee="", url=""):
        """ Extrait les infos de chacune des pages détaillées des résultats,
        via le résultat de beautifulsoup, via le code source de la page, ou via l'URL """
        
        if (soup == ""):
            if (page_html_detaillee == "") : page_html_detaillee = self._get(url)
            soup = BeautifulSoup(page_html_detaillee, _DEFAULT_BEAUTIFULSOUP_PARSER)
        
        nb_resultats_temp = self._normaliser_chaine(self._css_selector(soup,'td[class="enrichcontentbab"] > h2')[0].text)
        nb_resultats = int(nb_resultats_temp.split(u"a repéré")[1].split(u"titres")[0].strip())
        
        url_premier_resultat = self._css_selector(soup,'td[class="itemlisting"] > h1 > a')[0]['href']
        url_premier_resultat = urljoin(_URL_BASE,url_premier_resultat)
        
        liste_infos = []
        for indice_resultat in range(1,nb_resultats+1):
            #TODO : Ajouter le multithreading pour accélérer le traitement (22s pour 15 résultats)
            url_resultat = url_premier_resultat.replace(u"item=1", u"item=%d" % (indice_resultat))
            liste_infos.append(self._extraire_infos_page_detaillee(url=url_resultat))
        return liste_infos
    
    def _normaliser_chaine(self, chaine):
        return chaine.replace('\n',' ').replace('\r','').replace('\t',' ').replace('  ',' ').strip()
        
    def rechercher(self, titre="", auteur=""):
        liste_resultats = []
        
        page_html_resultats = self._get(self._construire_url_recherche(titre=titre, auteur=auteur))

        soup = BeautifulSoup(page_html_resultats, _DEFAULT_BEAUTIFULSOUP_PARSER)
        
        if soup.title : # L'objet n'existe pas s'il n'y a pas de balise <TITLE> dans la page HTML
            titre_page = soup.title.string
    
            if titre_page == _TITRE_PAGE_UN_RESULTAT: # S'il n'y a qu'un seul résultat, la page est directement celle détaillée
                liste_resultats.append(self._extraire_infos_page_detaillee(soup=soup))
        
            elif _TITRE_PAGE_PLUSIEURS_RESULTATS in titre_page:
                liste_resultats = self._extraire_infos_page_plusieurs_resultats(soup=soup)
        
            else :
                print("**Page avec titre inconnu**\n\n")
                print(titre_page)
        
        return liste_resultats