from sklearn.mixture import GaussianMixture
import time
import numpy as np
import pandas as pd
import warnings
from sklearn.metrics import roc_curve, auc

warnings.filterwarnings("ignore")



def nb_clust_with_bic_(coord_tc, min_nc=2, max_nc=20):
    """
    USAGE
    Compute a Gaussian mixture on the coord_tc dataset for number of cluster between min_nc and max_nc.
    Find best number of cluster according to the BIC criterion.
    Return the best number of cluster, the model according to best number of cluster and bic value of the model.

    INPUT
    coord_tc : numpy array of the coordinates
    min_nc : min number of cluster to test:
    max_nc : max_number of cluster to test

    OUTPUT
    nc : The best number of cluster according to the BIC criterion
    bic : bic value of the model
    gmm : model according to best number of cluster
    """
    max_ncf = min(max_nc, len(coord_tc))
    nc_bic = [-1, np.inf, []]
    for nc in range(min_nc, max_ncf):
        gmm = GaussianMixture(n_components=nc, covariance_type="full")
        gmm.fit(coord_tc)
        bic = gmm.bic(coord_tc)
        nc_bic = min([nc_bic, [nc, bic, gmm]], key=lambda x: x[1])
    nc, bic, gmm = nc_bic
    return nc, bic, gmm


def create_cumsum_data(data):
    """
    USAGE
    Compute cumsum for each "score column" of data according to id_traj column.

    INPUT
    data : pandas DataFrame

    OUTPUT
    data_cumsum : pandas DataFrame where each score columns represent cumulative sum of the different score
    according to id_traj columns
    """
    # scores_columns = list(filter(lambda c: c.startswith("score_"), data.columns))
    scores_columns = list([c for c in data.columns if c.startswith("score_")])

    data_cumsum = data.groupby("id_traj")[scores_columns].apply(lambda t: t.cumsum())
    return data_cumsum


def train_test_split(data_original, cv_index_i, i):
    """
    USAGE
    generate train and test dataset for cv group number i according of list of test id_traj within cv_index_i list.

    INPUT
    data_original : pandas DataFrame
    cv_index_i : list of id of trajectories which will be considered as test dataset
    cv group.

    OUTPUT
    traj_coord_train : numpy array. Coordinates of point within train dataset
    traj_coord_test : numpy array. Coordinates of point within test dataset
    data_ : pandasDataFrame. DataFrame with index of test dataset.
    """

    data_test_bool = data_original.id_traj.isin(cv_index_i)
    data_train = data_original[np.logical_not(data_test_bool)]
    traj_coord_train = data_train[["lons", "lats", "id_traj"]].values

    data_test = data_original[data_test_bool]
    traj_coord_test = data_test[["lons", "lats"]].values
    index_test = data_test.index
    data_ = pd.DataFrame(index=index_test)
    data_["cv"] = i
    return traj_coord_train, traj_coord_test, data_


def build_cross_clust_mixt_cv(data_original, cv_list, nb_traj_class, labels):
    """
    USAGE
    Compute a Gaussian mixture on the different train set in the cv_data dictionary with the best number of cluster
    according to the BIC criterion and reconstruct the data with their score corresponding to the different mixture.

    INPUT
    cv_data : List of Cross validation data generated by load_cv_data function
    pdic : dictionary of extra parameter containing the "cv_size" entry"
    data_index : index of the original data (for reconstruction)

    OUTPUT
    gmm_cv: list of the different gaussian mixture parameter for each cross validation and trajectory cluster
    data : reconstructed data with gmm score
    """
    gmm_cv = []
    cv_size = 10
    data_list = []
    for i, cv_index_i in enumerate(cv_list):
        ttime = time.asctime()
        print("CV: %d/%d, " % (i, cv_size) + ttime)

        # Build train/test dataset for CV number i
        traj_coord_train, traj_coord_test, data_ = train_test_split(data_original, cv_index_i, i)

        gmm_per_traj_clust = {}
        # Build Gaussian Mixture model for each cluster of trajectories
        for n_class in range(nb_traj_class):
            id_traj_class_n = np.where(labels == n_class)[0]
            coord_tc = traj_coord_train[np.isin(traj_coord_train[:, -1], id_traj_class_n)][:,:-1]
            n_ind = coord_tc.shape[0]
            if n_ind > 10000:
                coord_tc = coord_tc[np.random.choice(coord_tc.shape[0], size=10000, replace=False), :]
            nc, bic, gmm = nb_clust_with_bic_(coord_tc)

            # Update Gaussian mixture model dictionnary
            gmm_per_traj_clust.update({n_class: gmm})

            # Compute likelihood for all test dataset
            scores = gmm.score(traj_coord_test)

            # Update score
            data_["score_" + str(n_class)] = scores
        data_list.append(data_)
        gmm_cv.append(gmm_per_traj_clust)

    data = data_original.join(pd.concat(data_list).reindex(data_original.index))

    return gmm_cv, data





def create_roc_dict(data_original, data_score, labels, nb_tc):
    data_cumsum = create_cumsum_data(data_score)
    data_cumsum["id_traj"] = data_original.id_traj

    data_gbit = data_cumsum.groupby("id_traj").last()
    data_gbit["traj_clust"] = [labels[k] for k in data_gbit.index]

    roc_dic = {}
    for tc in range(nb_tc):
        y = data_gbit["traj_clust"] == tc
        scores = data_gbit["score_" + str(tc)].values

        fpr, tpr, thresholds = roc_curve(y, scores, pos_label=1)
        auc_v = auc(fpr, tpr)

        roc_dic.update({tc: (fpr, tpr, auc_v)})
    return roc_dic