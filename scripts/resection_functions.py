import multiprocessing as mp
import time
from typing import List, Tuple

import numpy as np
import scipy.linalg
import scipy.optimize
from multipledispatch import dispatch
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation as R

import scripts.liblie as ll
from scripts import theodolite_utils as tu
from scripts import theodolite_function as tf


def R_z(theta):
    R = np.eye(4)
    R[0, :2] = [np.cos(theta), -np.sin(theta)]
    R[1, :2] = [np.sin(theta), np.cos(theta)]
    return R

def T_z(theta, t):
    T = R_z(theta)
    T[:3, 3] = t
    return T

def dist(p, q):
    return np.linalg.norm(p[0:3] - q[0:3])

def T_z_so3(x, y, z, theta):
    T = np.eye(4, 4)
    T[:3, 3] = np.array([x, y, z])
    C = ll.expm_so3(ll.wedge_so3(np.array([0, 0, theta])))
    T[:3, :3] = C
    return T

def cost_fun_one_pose(X, ps1, ps2):
    T = T_z_so3(*X)
    c = 0
    for i in range(ps1.shape[1]):
        p1 = ps1[:, i]
        p2 = ps2[:, i]
        c += np.linalg.norm(p1 - T@p2)**2
    return c/ps1.shape[1]

def cost_fun(p1s_l, p2s_l, p3s_l, xi_12, xi_13, d_truth12, d_truth13, d_truth23):
    T12 = exp_T(xi_12)
    T13 = exp_T(xi_13)
    c = 0
    c += sum([(dist(p1, T12@p2) - d_truth12)**2 for p1, p2 in zip(p1s_l, p2s_l)])
    c += sum([(dist(p1, T13@p3) - d_truth13)**2 for p1, p3 in zip(p1s_l, p3s_l)])
    c += sum([(dist(T12@p2, T13@p3) - d_truth23)**2 for p2, p3 in zip(p2s_l, p3s_l)])

    return c

def cost_fun_ls(p1s_l, p2s_l, p3s_l, xi_12, xi_13, d_truth12, d_truth13, d_truth23):
    T12 = exp_T(xi_12)
    T13 = exp_T(xi_13)

    N = len(p1s_l)
    c = np.zeros((N*3))
    c[:N] = [(dist(p1, T12@p2) - d_truth12) for p1, p2 in zip(p1s_l, p2s_l)]
    c[N:2*N] = [(dist(p1, T13@p3) - d_truth13) for p1, p3 in zip(p1s_l, p3s_l)]
    c[2*N:] = [(dist(T12@p2, T13@p3) - d_truth23) for p2, p3 in zip(p2s_l, p3s_l)]
    return c/(3*N)

def cost_fun_ls_4dof(p1s_l, p2s_l, p3s_l, xi_12, xi_13, d_truth12, d_truth13, d_truth23):
    T12 = exp_T_4dof(xi_12)
    T13 = exp_T_4dof(xi_13)

    N = len(p1s_l)
    c = np.zeros((N*3))
    c[:N] = [(dist(p1, T12@p2) - d_truth12) for p1, p2 in zip(p1s_l, p2s_l)]
    c[N:2*N] = [(dist(p1, T13@p3) - d_truth13) for p1, p3 in zip(p1s_l, p3s_l)]
    c[2*N:] = [(dist(T12@p2, T13@p3) - d_truth23) for p2, p3 in zip(p2s_l, p3s_l)]
    return c/(3*N)

def vee(xi):  ## TODO: use LibLie wedge
    T = np.zeros((4, 4))
    T[:3, :3] = np.array([[0, -xi[2], xi[1]],
                          [xi[2], 0, -xi[0]],
                          [-xi[1], xi[0], 0]])
    T[:3, 3] = xi[3:]
    return T

def vee_4dof(xi):  ## TODO: use LibLie wedge
    T = np.zeros((4, 4))
    T[:3, :3] = np.array([[0, -xi[0], 0],
                          [xi[0], 0, 0],
                          [0, 0, 0]])
    T[:3, 3] = xi[1:]
    return T

def exp_T_4dof(xi):  ## TODO: use LibLie
    return scipy.linalg.expm(vee_4dof(xi))

def exp_T(xi):  ## TODO: use LibLie
    return scipy.linalg.expm(vee(xi))

def exp_inv_T(A):  ## TODO: use LibLie
    return scipy.linalg.logm(A)

def dynamic_vs_static_control_points_error_comparison(static_file_path: str, dynamic_file_path: str,
                                                      training_threshold: float = 0.75, nb_iterations: int = 50) -> list:
    """
    Compute the errors between dynamic and static control points.

    Parameters
    ----------
    static_file_path : str
        The path to the file containing the static control points. e.g. theodolite_reference_prisms.txt
    dynamic_file_path : str
        The path to the file containing the dynamic control points.
    training_threshold : float
        The threshold used to split the dynamic control points into the training and prediction dataset. Default = 0.75
    nb_iterations : int
        The number of iterations. Default = 50

    Returns
    -------
    errors : list
        Returns a list containing all the errors, both for the dynamic and static control points.
        The first list holds the errors for the dynamic control points and the second one for the static control points.
    """
    ts1_static, ts2_static, ts3_static, T1_static, T12_static, T13_static = tu.read_marker_file(
        file_name=static_file_path, theodolite_reference_frame=1)
    ts1_dynamic = tu.read_prediction_data_resection_csv_file(dynamic_file_path + "_1.csv")[:, 1:].T
    ts2_dynamic = tu.read_prediction_data_resection_csv_file(dynamic_file_path + "_2.csv")[:, 1:].T
    ts3_dynamic = tu.read_prediction_data_resection_csv_file(dynamic_file_path + "_3.csv")[:, 1:].T

    nb_points = ts1_dynamic.shape[1]
    dynamic_errors = []
    static_errors = []

    for it in range(nb_iterations):
        mask = tu.uniform_random_mask(nb_points, threshold=training_threshold)

        training_1 = ts1_dynamic[:, mask]
        training_2 = ts2_dynamic[:, mask]
        training_3 = ts3_dynamic[:, mask]

        prediction_1 = ts1_dynamic[:, ~mask]
        prediction_2 = ts2_dynamic[:, ~mask]
        prediction_3 = ts3_dynamic[:, ~mask]

        T12_dynamic = tu.point_to_point_minimization(training_2, training_1)
        T13_dynamic = tu.point_to_point_minimization(training_3, training_1)

        prediction_2_dynamic = T12_dynamic @ prediction_2
        prediction_3_dynamic = T13_dynamic @ prediction_3

        for i, j, k in zip(prediction_1.T, prediction_2_dynamic.T, prediction_3_dynamic.T):
            dist_12 = np.linalg.norm(i[0:3] - j[0:3]) * 1000
            dist_13 = np.linalg.norm(i[0:3] - k[0:3]) * 1000
            dist_23 = np.linalg.norm(j[0:3] - k[0:3]) * 1000
            dynamic_errors.append(dist_12)
            dynamic_errors.append(dist_13)
            dynamic_errors.append(dist_23)

        prediction_2_static = T12_static @ prediction_2
        prediction_3_static = T13_static @ prediction_3

        for i, j, k in zip(prediction_1.T, prediction_2_static.T, prediction_3_static.T):
            dist_12 = np.linalg.norm(i[0:3] - j[0:3]) * 1000
            dist_13 = np.linalg.norm(i[0:3] - k[0:3]) * 1000
            dist_23 = np.linalg.norm(j[0:3] - k[0:3]) * 1000
            static_errors.append(dist_12)
            static_errors.append(dist_13)
            static_errors.append(dist_23)
    print(ts1_static, '\n', ts2_static, '\n', ts3_static, '\n', T1_static, '\n', T12_static, '\n', T13_static, '\n', T12_dynamic, '\n', T13_dynamic)
    return [dynamic_errors, static_errors]

def static_control_points_error(static_file_path: str, exp_file_path: str = "", inter_prism_dist: list = [], training_threshold: float = 0.75, nb_iterations: int = 20) -> list:
    """
    Compute the errors between dynamic and static control points.

    Parameters
    ----------
    static_file_path : str
        The path to the file containing the static control points. e.g. theodolite_reference_prisms.txt
    training_threshold : float
        The threshold used to split the dynamic control points into the training and prediction dataset. Default = 0.75
    nb_iterations : int
        The number of iterations. Default = 20

    Returns
    -------
    errors : list
        Returns a list containing all the errors, for the static control points.
        The list holds the errors for the static control points.
    """
    ts1_static, ts2_static, ts3_static, T1_static, T12_static, T13_static = tu.read_marker_file(
        file_name=static_file_path, theodolite_reference_frame=1)

    nb_points = ts1_static.shape[1]
    static_errors = []
    exp_errors = []

    for it in range(nb_iterations):
        mask = tu.uniform_random_mask(nb_points, threshold=training_threshold)

        training_1 = ts1_static[:, mask]
        training_2 = ts2_static[:, mask]
        training_3 = ts3_static[:, mask]

        prediction_1 = ts1_static[:, ~mask]
        prediction_2 = ts2_static[:, ~mask]
        prediction_3 = ts3_static[:, ~mask]

        T12_trained = tu.point_to_point_minimization(training_2, training_1)
        T13_trained = tu.point_to_point_minimization(training_3, training_1)

        prediction_1_static = ts1_static
        prediction_2_static = T12_trained @ ts2_static
        prediction_3_static = T13_trained @ ts3_static

        for i, j, k in zip(prediction_1_static.T, prediction_2_static.T, prediction_3_static.T):
            dist_12 = np.linalg.norm(i[0:3] - j[0:3]) * 1000
            dist_13 = np.linalg.norm(i[0:3] - k[0:3]) * 1000
            dist_23 = np.linalg.norm(j[0:3] - k[0:3]) * 1000
            static_errors.append(dist_12)
            static_errors.append(dist_13)
            static_errors.append(dist_23)
        if exp_file_path != "":
            exp_errors += tf.inter_prism_distance_error_experiment(exp_file_path, [T1_static, T12_trained, T13_trained], inter_prism_dist)
    return static_errors,exp_errors

def dynamic_control_points_error_comparison(dynamic_file_path: str, exp_file_path: str = "", inter_prism_dist: list = [], training_threshold: float = 0.75, nb_iterations: int = 20, rate: float = 10, velocity_outlier: float = 2):
    """
    Compute the errors between dynamic and static control points.

    Parameters
    ----------
    dynamic_file_path : str
        The path to the file containing the dynamic control points.
    training_threshold : float
        The threshold used to split the dynamic control points into the training and prediction dataset. Default = 0.75
    nb_iterations : int
        The number of iterations. Default = 20

    Returns
    -------
    errors : list
        Returns a list containing all the errors, for the dynamic control points.
        The list holds the errors for the dynamic control points.
    """
    ts1_dynamic = tu.read_prediction_data_resection_csv_file(dynamic_file_path + "_1.csv")[:, 1:]
    ts2_dynamic = tu.read_prediction_data_resection_csv_file(dynamic_file_path + "_2.csv")[:, 1:]
    ts3_dynamic = tu.read_prediction_data_resection_csv_file(dynamic_file_path + "_3.csv")[:, 1:]

    if (ts1_dynamic.shape[1] > 0 and ts2_dynamic.shape[1] > 0 and ts3_dynamic.shape[1] > 0):
        speed_limit = velocity_outlier
        index = tu.find_not_moving_points_GP(ts1_dynamic, speed_limit, 1/rate)

        p1 = ts1_dynamic[index, :]
        p2 = ts2_dynamic[index, :]
        p3 = ts3_dynamic[index, :]

        nb_points = p1.T.shape[1]
        dynamic_errors = []
        errors_exp = []

        for it in range(nb_iterations):
            mask = tu.uniform_random_mask(nb_points, threshold=training_threshold)

            training_1 = p1.T[:, mask]
            training_2 = p2.T[:, mask]
            training_3 = p3.T[:, mask]

            prediction_1 = p1.T[:, ~mask]
            prediction_2 = p2.T[:, ~mask]
            prediction_3 = p3.T[:, ~mask]

            T12_dynamic = tu.point_to_point_minimization(training_2, training_1)
            T13_dynamic = tu.point_to_point_minimization(training_3, training_1)

            prediction_2_dynamic = T12_dynamic @ prediction_2
            prediction_3_dynamic = T13_dynamic @ prediction_3

            for i, j, k in zip(prediction_1.T, prediction_2_dynamic.T, prediction_3_dynamic.T):
                dist_12 = np.linalg.norm(i[0:3] - j[0:3]) * 1000
                dist_13 = np.linalg.norm(i[0:3] - k[0:3]) * 1000
                dist_23 = np.linalg.norm(j[0:3] - k[0:3]) * 1000
                dynamic_errors.append(dist_12)
                dynamic_errors.append(dist_13)
                dynamic_errors.append(dist_23)
            T1 = np.identity(4)
            if exp_file_path != "":
                errors_exp += tf.inter_prism_distance_error_experiment(exp_file_path, [T1, T12_dynamic, T13_dynamic], inter_prism_dist)
    return dynamic_errors, errors_exp


def inter_prism_resection(Inter_distance, file_name_path, path_type, path_file_type, file_name_marker, rate,
                          prior, velocity_outlier, threshold_training, number_iteration):
    dist_prism_new_all = []
    dist_prism_basic_all = []
    error_prism_new_all = []
    error_prism_basic_all = []

    for i_dist, k_file, fm in zip(Inter_distance, file_name_path, file_name_marker):
        print(k_file)
        trimble_1 = tu.read_prediction_data_resection_csv_file(k_file + path_type + path_file_type + "1.csv")
        trimble_2 = tu.read_prediction_data_resection_csv_file(k_file + path_type + path_file_type + "2.csv")
        trimble_3 = tu.read_prediction_data_resection_csv_file(k_file + path_type + path_file_type + "3.csv")

        if (len(np.array(trimble_1)) > 0 and len(np.array(trimble_2)) > 0 and len(np.array(trimble_3)) > 0):
            speed_limit = velocity_outlier
            index1 = tu.find_not_moving_points_GP(np.array(trimble_1), speed_limit, 1/rate)

            p1 = np.array(trimble_1)[index1, 1:5]
            p2 = np.array(trimble_2)[index1, 1:5]
            p3 = np.array(trimble_3)[index1, 1:5]

            # print(len(index))

            dist_prism_new = []
            dist_prism_basic = []
            error_new = []
            error_basic = []

            marker_1, marker_2, marker_3, T1_basic, T12_basic, T13_basic = tu.read_marker_file(fm, 1, 1)
            if(prior=="PTP"):
                T12_init = tu.point_to_point_minimization(p2.T, p1.T)
                T13_init = tu.point_to_point_minimization(p3.T, p1.T)
            else:
                if(prior=="CP"):
                    T12_init = T12_basic
                    T13_init = T13_basic

            T12_init_log = exp_inv_T(T12_init)
            T13_init_log = exp_inv_T(T13_init)

            x_init = [T12_init_log[2, 1], T12_init_log[0, 2], T12_init_log[1, 0], T12_init_log[0, 3],
                      T12_init_log[1, 3], T12_init_log[2, 3],
                      T13_init_log[2, 1], T13_init_log[0, 2], T13_init_log[1, 0], T13_init_log[0, 3],
                      T13_init_log[1, 3], T13_init_log[2, 3]]

            dist_12_t = i_dist[0]
            dist_13_t = i_dist[1]
            dist_23_t = i_dist[2]

            for num_it in range(0, number_iteration):
                print(num_it)
                mask = tu.random_splitting_mask(p1, threshold_training)
                p1_t = p1[mask]
                p2_t = p2[mask]
                p3_t = p3[mask]
                p1_p = p1[~mask]
                p2_p = p2[~mask]
                p3_p = p3[~mask]
                start_time = time.time()
                res = scipy.optimize.least_squares(lambda x: cost_fun_ls(p1_t,
                                                                         p2_t,
                                                                         p3_t,
                                                                         x[:6],
                                                                         x[6:],
                                                                         dist_12_t,
                                                                         dist_13_t,
                                                                         dist_23_t), x0=x_init, method='lm',
                                                   ftol=1e-15, xtol=1e-15, x_scale=1.0, loss='linear',
                                                   f_scale=1.0, diff_step=None, tr_solver=None, tr_options={},
                                                   jac_sparsity=None, max_nfev=30000000, verbose=2, args=(), kwargs={})
                stop_time = time.time()
                print(stop_time - start_time)
                xi_12 = res.x[:6]
                xi_13 = res.x[6:]
                T12 = exp_T(xi_12)
                T13 = exp_T(xi_13)
                T_1 = np.identity(4)
                p1t = (T_1@p1_p.T).T
                p2t = (T12@p2_p.T).T
                p3t = (T13@p3_p.T).T

                for i_n in range(0, len(p1t) - 1):
                    dp1 = abs(np.linalg.norm(p1t[i_n, 0:3] - p2t[i_n, 0:3]) - dist_12_t)*1000
                    dp2 = abs(np.linalg.norm(p1t[i_n, 0:3] - p3t[i_n, 0:3]) - dist_13_t)*1000
                    dp3 = abs(np.linalg.norm(p3t[i_n, 0:3] - p2t[i_n, 0:3]) - dist_23_t)*1000
                    dist_prism_new.append(dp1)
                    dist_prism_new.append(dp2)
                    dist_prism_new.append(dp3)

                    dp1 = abs(np.linalg.norm(p1_p[i_n, 0:3] - (T12_basic@p2_p[i_n, 0:4].T)[0:3]) - dist_12_t)*1000
                    dp2 = abs(np.linalg.norm(p1_p[i_n, 0:3] - (T13_basic@p3_p[i_n, 0:4].T)[0:3]) - dist_13_t)*1000
                    dp3 = abs(np.linalg.norm((T13_basic@p3_p[i_n, 0:4].T)[0:3] - (T12_basic@p2_p[i_n, 0:4].T)[
                                                                                 0:3]) - dist_23_t)*1000
                    dist_prism_basic.append(dp1)
                    dist_prism_basic.append(dp2)
                    dist_prism_basic.append(dp3)

                m1_b = marker_1
                m2_b = T12_basic@marker_2
                m3_b = T13_basic@marker_3

                m1_n = marker_1
                m2_n = T12@marker_2
                m3_n = T13@marker_3

                compute_error_between_points(m1_b, m2_b, m3_b, error_basic)
                compute_error_between_points(m1_n, m2_n, m3_n, error_new)

            dist_prism_new_all.append(dist_prism_new)
            dist_prism_basic_all.append(dist_prism_basic)
            error_prism_new_all.append(error_new)
            error_prism_basic_all.append(error_basic)

        else:
            print("No data in file(s) " + k_file + "  !!")
    print("Results done !")

    return dist_prism_new_all, dist_prism_basic_all, error_prism_new_all, error_prism_basic_all

def one_inter_prism_resection(Inter_distance, file_name, file_name_marker, rate: float=10, prior: str="CP", velocity_outlier: float = 1,
                              threshold_training: float = 0.75, number_iteration: int = 5):
    dist_prism_new_all = []
    dist_prism_basic_all = []
    error_prism_new_all = []
    error_prism_basic_all = []
    exp_errors = []

    trimble_1 = tu.read_prediction_data_resection_csv_file(file_name + "1.csv")
    trimble_2 = tu.read_prediction_data_resection_csv_file(file_name + "2.csv")
    trimble_3 = tu.read_prediction_data_resection_csv_file(file_name + "3.csv")

    if (len(np.array(trimble_1)) > 0 and len(np.array(trimble_2)) > 0 and len(np.array(trimble_3)) > 0):
        speed_limit = velocity_outlier
        index1 = tu.find_not_moving_points_GP(np.array(trimble_1), speed_limit, 1/rate)

        p1 = np.array(trimble_1)[index1, 1:5]
        p2 = np.array(trimble_2)[index1, 1:5]
        p3 = np.array(trimble_3)[index1, 1:5]

        dist_prism_new = []
        dist_prism_basic = []
        error_new = []
        error_basic = []

        if(len(index1)>6):

            marker_1, marker_2, marker_3, T1_basic, T12_basic, T13_basic = tu.read_marker_file(file_name_marker, 1, 1)
            if(prior=="PTP"):
                T12_init = tu.point_to_point_minimization(p2.T, p1.T)
                T13_init = tu.point_to_point_minimization(p3.T, p1.T)
            else:
                if(prior=="CP"):
                    T12_init = T12_basic
                    T13_init = T13_basic

            T12_init_log = exp_inv_T(T12_init)
            T13_init_log = exp_inv_T(T13_init)

            x_init = [T12_init_log[2, 1], T12_init_log[0, 2], T12_init_log[1, 0], T12_init_log[0, 3],
                      T12_init_log[1, 3], T12_init_log[2, 3],
                      T13_init_log[2, 1], T13_init_log[0, 2], T13_init_log[1, 0], T13_init_log[0, 3],
                      T13_init_log[1, 3], T13_init_log[2, 3]]

            dist_12_t = Inter_distance[0]
            dist_13_t = Inter_distance[1]
            dist_23_t = Inter_distance[2]

            for num_it in range(0, number_iteration):
                print(num_it)
                mask = tu.random_splitting_mask(p1, threshold_training)
                p1_t = p1[mask]
                p2_t = p2[mask]
                p3_t = p3[mask]
                p1_p = p1[~mask]
                p2_p = p2[~mask]
                p3_p = p3[~mask]
                start_time = time.time()
                res = scipy.optimize.least_squares(lambda x: cost_fun_ls(p1_t,
                                                                         p2_t,
                                                                         p3_t,
                                                                         x[:6],
                                                                         x[6:],
                                                                         dist_12_t,
                                                                         dist_13_t,
                                                                         dist_23_t), x0=x_init, method='lm',
                                                   ftol=1e-15, xtol=1e-15, x_scale=1.0, loss='linear',
                                                   f_scale=1.0, diff_step=None, tr_solver=None, tr_options={},
                                                   jac_sparsity=None, max_nfev=30000000, verbose=2, args=(), kwargs={})
                stop_time = time.time()
                print("Time [s]: ", stop_time - start_time)
                xi_12 = res.x[:6]
                xi_13 = res.x[6:]
                T12 = exp_T(xi_12)
                T13 = exp_T(xi_13)
                T_1 = np.identity(4)
                p1t = (T_1@p1_p.T).T
                p2t = (T12@p2_p.T).T
                p3t = (T13@p3_p.T).T

                for i_n in range(len(p1t)):
                    dp1 = abs(np.linalg.norm(p1t[i_n, 0:3] - p2t[i_n, 0:3]) - dist_12_t)*1000
                    dp2 = abs(np.linalg.norm(p1t[i_n, 0:3] - p3t[i_n, 0:3]) - dist_13_t)*1000
                    dp3 = abs(np.linalg.norm(p3t[i_n, 0:3] - p2t[i_n, 0:3]) - dist_23_t)*1000
                    dist_prism_new.append(dp1)
                    dist_prism_new.append(dp2)
                    dist_prism_new.append(dp3)

                    dp1 = abs(np.linalg.norm(p1_p[i_n, 0:3] - (T12_basic@p2_p[i_n, 0:4].T)[0:3]) - dist_12_t)*1000
                    dp2 = abs(np.linalg.norm(p1_p[i_n, 0:3] - (T13_basic@p3_p[i_n, 0:4].T)[0:3]) - dist_13_t)*1000
                    dp3 = abs(np.linalg.norm((T13_basic@p3_p[i_n, 0:4].T)[0:3] - (T12_basic@p2_p[i_n, 0:4].T)[
                                                                                 0:3]) - dist_23_t)*1000
                    dist_prism_basic.append(dp1)
                    dist_prism_basic.append(dp2)
                    dist_prism_basic.append(dp3)

                m1_b = marker_1
                m2_b = T12_basic@marker_2
                m3_b = T13_basic@marker_3

                m1_n = marker_1
                m2_n = T12@marker_2
                m3_n = T13@marker_3

                compute_error_between_points(m1_b, m2_b, m3_b, error_basic)
                compute_error_between_points(m1_n, m2_n, m3_n, error_new)
                exp_errors += tf.inter_prism_distance_error_experiment(file_name, [T_1, T12, T13], Inter_distance)

        dist_prism_new_all.append(dist_prism_new)
        dist_prism_basic_all.append(dist_prism_basic)
        error_prism_new_all.append(error_new)
        error_prism_basic_all.append(error_basic)

    else:
        print("No data in file(s) " + k + "  !!")

    print("Results done !")

    return dist_prism_new_all[0], dist_prism_basic_all[0], error_prism_new_all[0], error_prism_basic_all[0], exp_errors


def compute_error_between_three_points(point_1: NDArray, point_2: NDArray, point_3: NDArray) -> List[NDArray]:
    """
    Compute the error between three points that are the same point coming from three different sources.

    Parameters
    ----------
    point_1: ndarray
    point_2: ndarray
    point_3: ndarray

    Returns
    -------
    A list containing the errors between each point, i.e. the error between the following combinations: 1-2, 1-3 and 2-3.
    """
    error_12 = np.linalg.norm(point_1[:3] - point_2[:3])
    error_13 = np.linalg.norm(point_1[:3] - point_3[:3])
    error_23 = np.linalg.norm(point_2[:3] - point_3[:3])
    return [error_12, error_13, error_23]


def compute_error_between_points(m1_n, m2_n, m3_n, error):
    for i, j, k in zip(m1_n.T, m2_n.T, m3_n.T):
        dist_12 = np.linalg.norm(i[0:3] - j[0:3])
        dist_13 = np.linalg.norm(i[0:3] - k[0:3])
        dist_23 = np.linalg.norm(k[0:3] - j[0:3])
        error.append(dist_12)
        error.append(dist_13)
        error.append(dist_23)


@dispatch(np.ndarray, np.ndarray, np.ndarray, np.ndarray, str="", list=[])
def geomatic_resection_optimization_on_pose(trimble_1: NDArray, trimble_2: NDArray, trimble_3: NDArray, pillars_ref: NDArray, exp_file_name: str = "", inter_prism_dist: list = []) -> \
        Tuple[NDArray, NDArray, NDArray, NDArray, NDArray, NDArray, List[float], List[float], List[float], List[float], List[float]]:
    TF1 = tu.point_to_point_minimization(trimble_1, pillars_ref)
    R1 = TF1[0:3, 0:3]
    roll_pitch_yaw_1 = R.from_matrix(R1).as_euler('xyz')
    x1 = [0, 0, 0, roll_pitch_yaw_1[2]]

    TF2 = tu.point_to_point_minimization(trimble_2, pillars_ref)
    R2 = TF2[0:3, 0:3]
    roll_pitch_yaw_2 = R.from_matrix(R2).as_euler('xyz')
    x2 = [0, 0, 0, roll_pitch_yaw_2[2]]

    TF3 = tu.point_to_point_minimization(trimble_3, pillars_ref)
    R3 = TF3[0:3, 0:3]
    roll_pitch_yaw_3 = R.from_matrix(R3).as_euler('xyz')
    x3 = [0, 0, 0, roll_pitch_yaw_3[2]]

    subsets = [[1, 1, 0, 0],
               [1, 0, 1, 0],
               [1, 0, 0, 1],
               [0, 1, 1, 0],
               [0, 1, 0, 1],
               [0, 0, 1, 1]]
    method = 'TNC'
    tol = 1e-10
    options = {'maxfun': 500}

    error_exp = []
    error_all = []
    errors1 = []
    errors2 = []
    errors3 = []
    for subset in subsets:
        mask = np.array(subset, dtype=bool)
        pillars_t = pillars_ref[:, mask]
        pillars_c = pillars_ref[:, ~mask]
        ps1 = trimble_1[:, mask]
        ps2 = trimble_2[:, mask]
        ps3 = trimble_3[:, mask]
        ps1_c = trimble_1[:, ~mask]
        ps2_c = trimble_2[:, ~mask]
        ps3_c = trimble_3[:, ~mask]

        with mp.Pool(processes=3) as p:
            res1 = p.apply(scipy.optimize.minimize,
                           kwds={
                                   "fun": cost_fun_one_pose,
                                   "x0": x1,
                                   "args": (pillars_t, ps1),
                                   "method": method,
                                   "tol": tol,
                                   "options": options})
            res2 = p.apply(scipy.optimize.minimize,
                           kwds={
                                   "fun": cost_fun_one_pose,
                                   "x0": x2,
                                   "args": (pillars_t, ps2),
                                   "method": method,
                                   "tol": tol,
                                   "options": options})
            res3 = p.apply(scipy.optimize.minimize,
                           kwds={
                                   "fun": cost_fun_one_pose,
                                   "x0": x3,
                                   "args": (pillars_t, ps3),
                                   "method": method,
                                   "tol": tol,
                                   "options": options})

        TW1 = T_z_so3(*res1.x)
        TW2 = T_z_so3(*res2.x)
        TW3 = T_z_so3(*res3.x)

        # ============================================================
        # eval solution
        trimble_1_w = TW1@ps1_c
        trimble_2_w = TW2@ps2_c
        trimble_3_w = TW3@ps3_c
        # trimble_1_w = TW1@ps1
        # trimble_2_w = TW2@ps2
        # trimble_3_w = TW3@ps3
        compute_error_between_points(trimble_1_w, trimble_2_w, trimble_3_w, error_all)

        verrors1 = pillars_c - trimble_1_w
        for i in range(verrors1.shape[1]):
            errors1 += [np.linalg.norm(verrors1[:, i])*1000]

        verrors2 = pillars_c - trimble_2_w
        for i in range(verrors2.shape[1]):
            errors2 += [np.linalg.norm(verrors2[:, i])*1000]

        verrors3 = pillars_c - trimble_3_w
        for i in range(verrors3.shape[1]):
            errors3 += [np.linalg.norm(verrors3[:, i])*1000]

        if exp_file_name != "":
            error_exp += tf.inter_prism_distance_error_experiment(exp_file_name, [TW1, TW2, TW3], inter_prism_dist)

        # verrors1 = pillars_t - trimble_1_w
        # for i in range(verrors1.shape[1]):
        #     errors1 += [np.linalg.norm(verrors1[:, i])*1000]
        #
        # verrors2 = pillars_t - trimble_2_w
        # for i in range(verrors2.shape[1]):
        #     errors2 += [np.linalg.norm(verrors2[:, i])*1000]
        #
        # verrors3 = pillars_t - trimble_3_w
        # for i in range(verrors3.shape[1]):
        #     errors3 += [np.linalg.norm(verrors3[:, i])*1000]

    return TW1, TW2, TW3, TW1@trimble_1, TW2@trimble_2, TW3@trimble_3, error_all, errors1, errors2, errors3, error_exp


@dispatch(str, np.ndarray, str, list)
def geomatic_resection_optimization_on_pose(file_name: str, pillars_ref: NDArray, exp_file_name: str = "", inter_prism_dist: list = []):
    trimble_1, trimble_2, trimble_3, _, _, _ = tu.read_marker_file(file_name)
    return geomatic_resection_optimization_on_pose(trimble_1, trimble_2, trimble_3, pillars_ref, exp_file_name, inter_prism_dist)


def cartesian_2_spherical_coords(x: float, y: float, z: float) -> NDArray:
    """
    Convert a point's cartesian coordinates to spherical coordinates.

    Parameters
    ----------
    x: float
        The x coordinate of a 3D point.
    y: float
        The y coordinate of a 3D point.
    z: float
        The z coordinate of a 3D point.

    Returns
    -------
    ndarray
        Returns the distance, the vertical angle and the horizontal angle coordinates, in radians, of a 3D point in cartesian coordinates.
    """
    distance = np.linalg.norm([x, y, z])
    if distance == 0.:
        vertical_angle = 0.
    else:
        vertical_angle = np.arccos(z/distance)
    if x == 0. and y == 0.:
        horizontal_angle = 0.
    else:
        horizontal_angle = np.pi/2. - np.arctan2(y, x)

    return np.array([distance, vertical_angle, horizontal_angle])


def spherical_2_cartesian_coords(distance: float, vertical_angle: float, horizontal_angle: float) -> NDArray:
    """
    Convert a point's spherical coordinates to cartesian coordinates.

    Parameters
    ----------
    distance: float
        The slope distance measured by a total station in meter.
    vertical_angle: float
        The vertical angle in radian measured by a total station in radian. Z-axis reference.
    horizontal_angle: float
        The horizontal angle measured by a total station in radian. Y-axis reference and clockwise.

    Returns
    -------
    ndarray
        Returns the x, y and z coordinates of the 3D point in spherical coordinates.
    """
    x = distance*np.cos(np.pi/2 - horizontal_angle)*np.sin(vertical_angle)
    y = distance*np.sin(np.pi/2 - horizontal_angle)*np.sin(vertical_angle)
    z = distance*np.cos(vertical_angle)

    return np.array([x, y, z])


def calculate_tf_angle_using_scalar_product(reference_1: NDArray, reference_2: NDArray, reading_1: NDArray, reading_2: NDArray) -> NDArray:
    """
    Compute the angle between two pair of points from two different frames.

    The translation from the reading frame to the reference frame must have been applied prior to compute the angle.

    Parameters
    ----------
    reference_1: ndarray
        The first point's cartesian coordinates in the reference frame.
    reference_2: ndarray
        The second point's cartesian coordinates in the reference frame.
    reading_1: ndarray
        The first point's cartesian coordinates in the reading frame.
    reading_2: ndarray
        The second point's cartesian coordinates in the reading frame.

    Returns
    -------
    ndarray
        Return the angle between two pair of point in two different frames encoded into a 3D rigid transformation matrix.
    """
    ref_line = reference_1[:2] - reference_2[:2]
    ts_line = reading_1[:2] - reading_2[:2]
    angle = np.arccos(np.dot(ref_line, ts_line)/(np.linalg.norm(ts_line)*np.linalg.norm(ref_line)))

    if reading_1[0] > reading_2[0]:
        angle = -angle

    return T_z(angle, np.zeros(3))


def resection_with_2_known_points(reference_point_1: NDArray, reference_point_2: NDArray, reading_point_1: NDArray, reading_point_2: NDArray) -> Tuple[NDArray, NDArray]:
    """
    Compute the position and orientation of a total station based on two reference points and their respective reading made by the total station.

    The reference points must be in the cartesian coordinate system, i.e. [x, y, z] and the measured points must be in the spherical coordinate system, i.e. [elevation, azimuth, distance].

    Parameters
    ----------
    reference_point_1 : ndarray
        Cartesian coordinates, i.e. [x, y, z], of the first reference point.
    reference_point_2 : ndarray
        Cartesian coordinates, i.e. [x, y, z], of the second reference point.
    reading_point_1 : ndarray
        Spherical coordinates, i.e. [distance, elevation, azimuth], of the first reference point measured by the total station.
    reading_point_2 : ndarray
        Spherical coordinates, i.e. [distance, elevation, azimuth], of the second reference point measured by the total station.

    Returns
    -------
    list[ndarray]
        A list of the two possible position and orientation of the total station.
    """
    x_1, y_1, z_1 = reference_point_1
    x_2, y_2, z_2 = reference_point_2
    distance_1, elevation_1, _ = reading_point_1
    distance_2, elevation_2, _ = reading_point_2

    z = np.mean([z_1 - distance_1*np.cos(elevation_1), z_2 - distance_2*np.cos(elevation_2)])

    # find the position of the total station using the intersection of 2 circles given by the measurements of the prism position.
    radius_1 = distance_1*np.sin(elevation_1)
    radius_2 = distance_2*np.sin(elevation_2)

    delta_y = y_2 - y_1

    # find the value of y based on the circles' radius and the reference points
    if delta_y != 0:
        y = (radius_1**2 - radius_2**2 - y_1**2 + y_2**2)/(2*delta_y)
    else:
        y = 0

    # find the possible values of x based on the y value
    x_1_1 = np.sqrt(radius_1**2 - (y - y_1)**2) + x_1
    x_1_2 = np.sqrt(radius_2**2 - (y - y_2)**2) + x_2
    x_2_1 = -np.sqrt(radius_1**2 - (y - y_1)**2) + x_1
    x_2_2 = -np.sqrt(radius_2**2 - (y - y_2)**2) + x_2

    x_1 = np.mean([x_1_1, x_1_2])
    x_2 = np.mean([x_2_1, x_2_2])

    position_1 = np.array([x_1, y, z, 0, 0, 0])
    position_2 = np.array([x_2, y, z, 0, 0, 0])

    TF1 = tu.tf_from_pose_roll_pitch_yaw(position_1)
    TF2 = tu.tf_from_pose_roll_pitch_yaw(position_2)

    reading_1_homogeneous = np.append(spherical_2_cartesian_coords(*reading_point_1), 1)
    reading_2_homogeneous = np.append(spherical_2_cartesian_coords(*reading_point_2), 1)

    R1 = calculate_tf_angle_using_scalar_product(reference_point_1, reference_point_2, TF1@reading_1_homogeneous, TF1@reading_2_homogeneous)
    R2 = calculate_tf_angle_using_scalar_product(reference_point_1, reference_point_2, TF2@reading_1_homogeneous, TF2@reading_2_homogeneous)

    TF1 = TF1@R1
    TF2 = TF2@R2

    return TF1, TF2
