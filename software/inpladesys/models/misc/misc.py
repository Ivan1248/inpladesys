from inpladesys.datatypes import Segment, Segmentation
from typing import List
import numpy as np
from inpladesys.datatypes.dataset import Dataset
from collections import Counter
from sklearn.model_selection import train_test_split


def generate_segmentation(preprocessed_documents: List[List[tuple]], documents_features: List[np.ndarray],
             document_label_lists, documents) -> List[Segmentation]:
    assert len(documents_features) == len(preprocessed_documents)
    segmentations = []
    for i in range(len(documents_features)):
        preprocessed_doc_tokens = preprocessed_documents[i]
        doc_features = documents_features[i]
        assert doc_features.shape[0] == len(preprocessed_doc_tokens)
        labels = document_label_lists[i]
        segments = []
        for k in range(doc_features.shape[0]):
            prep_token = preprocessed_doc_tokens[k]
            segments.append(Segment(offset=prep_token[1],
                                    length=prep_token[2] - prep_token[1],
                                    author=labels[k]))
        segmentations.append(Segmentation(author_count=max(labels) + 1,
                                          segments=segments,
                                          max_repairable_error=60,
                                          document_length=len(documents[i])))
    return segmentations


def custom_train_test_split(preprocessed_documents: List[List[tuple]], documents_features: List[np.ndarray],
                            dataset: Dataset, train_size, random_state):

    # indices of every document
    indices_of_docs = [i for i in range(len(preprocessed_documents))]

    i_train, i_test = train_test_split(indices_of_docs, train_size=train_size, random_state=random_state)

    prep_docs_train = [preprocessed_documents[i] for i in i_train]
    prep_docs_test = [preprocessed_documents[i] for i in i_test]

    doc_features_train = [documents_features[i] for i in i_train]
    doc_features_test = [documents_features[i] for i in i_test]

    author_counts_train = [dataset.segmentations[i].author_count for i in i_train]
    author_counts_test = [dataset.segmentations[i].author_count for i in i_test]

    dataset_train = Dataset([dataset.documents[i] for i in i_train],
                            [dataset.segmentations[i] for i in i_train])

    dataset_test = Dataset([dataset.documents[i] for i in i_test],
                           [dataset.segmentations[i] for i in i_test])

    return prep_docs_train, prep_docs_test, \
        doc_features_train, doc_features_test, \
        author_counts_train, author_counts_test, \
        dataset_train, dataset_test


def find_cluster_for_noisy_samples(predicted_labels, context_size=10):
    noisy = 0
    len_ = len(predicted_labels)
    for i in range(len_):
        if predicted_labels[i] == -1:
            noisy += 1
            left_diff = i-context_size
            left = left_diff if left_diff >= 0 else 0
            right_diff = i+context_size
            right = right_diff if right_diff < len_ else len_-1
            counter = Counter(predicted_labels[left:right+1])
            found, curr = 0, 0
            while found == 0:
                if counter.most_common()[curr][0] != -1:
                    predicted_labels[i] = counter.most_common()[curr][0]
                    found = 1
                curr += 1
    return noisy
