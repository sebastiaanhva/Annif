"""Support for subjects loaded from a SKOS/RDF file"""

import collections
import os.path
import shutil

import annif.util

from .types import Subject, SubjectCorpus


def serialize_subjects_to_skos(subjects, path):
    """Create a SKOS representation of the given subjects and serialize it
    into a SKOS/Turtle file with the given path name."""
    import joblib
    import rdflib
    from rdflib.namespace import RDF, SKOS

    graph = rdflib.Graph()
    graph.namespace_manager.bind("skos", SKOS)
    for subject in subjects:
        graph.add((rdflib.URIRef(subject.uri), RDF.type, SKOS.Concept))
        for lang, label in subject.labels.items():
            graph.add(
                (
                    rdflib.URIRef(subject.uri),
                    SKOS.prefLabel,
                    rdflib.Literal(label, lang),
                )
            )
        graph.add(
            (
                rdflib.URIRef(subject.uri),
                SKOS.notation,
                rdflib.Literal(subject.notation),
            )
        )
    graph.serialize(destination=path, format="turtle")
    # also dump the graph in joblib format which is faster to load
    annif.util.atomic_save(
        graph, *os.path.split(path.replace(".ttl", ".dump.gz")), method=joblib.dump
    )


class SubjectFileSKOS(SubjectCorpus):
    """A subject corpus that uses SKOS files"""

    _languages = None

    def __init__(self, path):
        import rdflib

        self.rdflib = rdflib
        self.OWL = rdflib.namespace.OWL
        self.RDF = rdflib.namespace.RDF
        self.RDFS = rdflib.namespace.RDFS
        self.SKOS = rdflib.namespace.SKOS

        self.PREF_LABEL_PROPERTIES = (self.SKOS.prefLabel, self.RDFS.label)
        self.path = path
        if path.endswith(".dump.gz"):
            import joblib

            self.graph = joblib.load(path)
        else:
            self.graph = rdflib.Graph()
            self.graph.parse(self.path, format=rdflib.util.guess_format(self.path))

    @property
    def languages(self):
        if self._languages is None:
            self._languages = {
                label.language
                for concept in self.concepts
                for label_type in self.PREF_LABEL_PROPERTIES
                for label in self.graph.objects(concept, label_type)
                if label.language is not None
            }
        return self._languages

    def _concept_labels(self, concept):
        by_lang = self.get_concept_labels(concept, self.PREF_LABEL_PROPERTIES)
        return {
            lang: by_lang[lang][0]
            if by_lang[lang]  # correct lang
            else by_lang[None][0]
            if by_lang[None]  # no language
            else self.graph.namespace_manager.qname(concept)
            for lang in self.languages
        }

    @property
    def subjects(self):
        for concept in self.concepts:
            labels = self._concept_labels(concept)

            notation = self.graph.value(concept, self.SKOS.notation, None, any=True)
            if notation is not None:
                notation = str(notation)

            yield Subject(uri=str(concept), labels=labels, notation=notation)

    @property
    def concepts(self):
        for concept in self.graph.subjects(self.RDF.type, self.SKOS.Concept):
            if (concept, self.OWL.deprecated, self.rdflib.Literal(True)) in self.graph:
                continue
            yield concept

    def get_concept_labels(self, concept, label_types):
        """return all the labels of the given concept with the given label
        properties as a dict-like object where the keys are language codes
        and the values are lists of labels in that language"""
        labels_by_lang = collections.defaultdict(list)

        for label_type in label_types:
            for label in self.graph.objects(concept, label_type):
                labels_by_lang[label.language].append(str(label))

        return labels_by_lang

    @staticmethod
    def is_rdf_file(path):
        """return True if the path looks like an RDF file that can be loaded
        as SKOS"""
        import rdflib.util

        fmt = rdflib.util.guess_format(path)
        return fmt is not None

    def save_skos(self, path):
        """Save the contents of the subject vocabulary into a SKOS/Turtle
        file with the given path name."""

        if self.path.endswith(".ttl"):
            # input is already in Turtle syntax, no need to reserialize
            if not os.path.exists(path) or not os.path.samefile(self.path, path):
                shutil.copyfile(self.path, path)
        else:
            # need to serialize into Turtle
            self.graph.serialize(destination=path, format="turtle")
        # also dump the graph in joblib format which is faster to load
        import joblib

        annif.util.atomic_save(
            self.graph,
            *os.path.split(path.replace(".ttl", ".dump.gz")),
            method=joblib.dump
        )
