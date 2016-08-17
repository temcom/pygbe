import numpy
import time

from pygbe.tree.FMMutils import addSources, sortPoints, generateTree, findTwigs
from pygbe.tree.direct import computeDiagonal
from pygbe.util.semi_analytical import GQ_1D
from pygbe.quadrature import quadratureRule_fine


class Event():
    """
    Class for logging like in pycuda's cuda.Event()
    """

    def __init__(self):
        self.t = 0
    def record(self):
        t = time.time()*1e3
    def time_till(self,toc):
        return toc.t-self.t
    def synchronize(self):
        pass


class Surface():
    """
    Surface class.
    It contains information about the solvent excluded surface.

    Attributes
    -----------

    triangle      : list, indices to triangle vertices.
    vertex        : list, position of vertices.
    XinV          : list, weights input for single layer potential.
    XinK          : list, weights input for double layer potential.
    Xout_int      : list, output vector of interior operators.
    Xout_ext      : list, output vector of exterior operators.
    xi            : list, x component of center.
    yi            : list, y component of center.
    zi            : list, z component of center.
    xj            : list, x component of gauss nodes.
    yj            : list, y component of gauss nodes.
    zj            : list, z component of gauss nodes.
    Area          : list, areas of triangles.
    normal        : list, normal of triangles.
    sglInt_int    : list, singular integrals for V for internal equation.
    sglInt_ext    : list, singular integrals for V for external equation.
    xk            : list, position of gauss points on edges.
    wk            : list, weight of gauss points on edges.
    Xsk           : list, position of gauss points for near singular integrals.
    Wsk           : list, weight of gauss points for near singular integrals.
    tree          : list, tree structure.
    twig          : list, tree twigs.
    xiSort        : list, sorted x component of center.
    yiSort        : list, sorted y component of center.
    ziSort        : list, sorted z component of center.
    xjSort        : list, sorted x component of gauss nodes.
    yjSort        : list, sorted y component of gauss nodes.
    zjSort        : list, sorted z component of gauss nodes.
    xcSort        : list, sorted x component of the box centers according to
                          M2P_list array.
    ycSort        : list, sorted y component of the box centers according to
                          M2P_list array.
    zcSort        : list, sorted z component of the box centers according to
                          M2P_list array.
    AreaSort      : list, sorted array of areas.
    sglInt_intSort: list, sorted array of singular integrals for V for internal
                          equation.
    sglInt_extSort: list, sorted array of singular integrals for V for external
                          equation.
    unsort        : list, array of indices to unsort targets.
    triangleSort  : list, sorted array of triangles.
    sortTarget    : list, indices to sort targets.
    sortSource    : list, indices to sort sources.
    offsetSource  : list, offsets to sorted source array.
    offsetTarget  : list, offsets to sorted target array.
    sizeTarget    : list, number of targets per twig.
    offsetTwigs   : list, offset to twig in P2P list array.
    P2P_list      : list, pointers to twigs for P2P interaction list.
    offsetMlt     : list, offset to multipoles in M2P list array.
    M2P_list      : list, pointers to boxes for M2P interaction list.
    Precond       : list, sparse representation of preconditioner for self
                          interaction block.
    Ein           : float, permitivitty inside surface.
    Eout          : float, permitivitty outside surface.
    E_hat         : float, ratio of Ein/Eout.
    kappa_in      : float, kappa inside surface.
    kappa_out     : float, kappa inside surface.
    LorY_in       : int, Laplace (1) or Yukawa (2) in inner region.
    LorY_out      : int, Laplace (1) or Yukawa (2) in outer region.
    surf_type     : int, Surface type: internal_cavity (=0), stern or
                         dielecric_interface (=1).
    phi0          : list, known surface potential (dirichlet) or derivative of
                          potential (neumann).
    phi           : list, potential on surface.
    dphi          : list, derivative of potential on surface.

    # Device data:

    xiDev        : list, sorted x component of center (on the GPU).
    yiDev        : list, sorted y component of center (on the GPU).
    ziDev        : list, sorted z component of center (on the GPU).
    xjDev        : list, sorted x component of gauss nodes (on the GPU).
    yjDev        : list, sorted y component of gauss nodes (on the GPU).
    zjDev        : list, sorted z component of gauss nodes (on the GPU).
    xcDev        : list, sorted x component of the box centers according to
                         M2P_list array (on the GPU).
    ycDev        : list, sorted y component of the box centers according to
                         M2P_list array (on the GPU).
    zcDev        : list, sorted z component of the box centers according to
                         M2P_list array (on the GPU).
    AreaDev      : list, areas of triangles (on the GPU).
    sglInt_intDev: list, singular integrals for V for internal equation (on the
                         GPU).
    sglInt_extDev: list, singular integrals for V for external equation (on the
                         GPU).
    vertexDev    : list, sorted vertex of the triangles.
    sizeTarDev   : list, number of targets per twig (on the GPU).
    offSrcDev    : list, offsets to sorted source array (on the GPU).
    offMltDev    : list, offset to multipoles in M2P list array (on the GPU).
    offTwgDev    : list, offset to twig in P2P list array (on the GPU).
    M2P_lstDev   : list, pointers to boxes for M2P interaction list (on the GPU).
    P2P_lstDev   : list, pointers to twigs for P2P interaction list (on the GPU).
    xkDev        : list, position of gauss points on edges (on the GPU).
    wkDev        : list, weight of gauss points on edges (on the GPU).
    XskDev       : list, position of gauss points for near singular integrals
                         (on the GPU).
    WskDev       : list, weight of gauss points for near singular integrals (on
                         the GPU).
    kDev         : list, quadrature number of each quadrature point, in order.
                         (on the GPU)
    """

    def __init__(self):
        self.twig = []

    def fill_surface(self, param):
        """
        Fill the surface with all the necessary information to solve it.

        -Set the Gauss points.
        -Generate tree, compute the indices and precompute terms for M2M.
        -Generate preconditioner.
        -Compute the diagonal integral for internal and external equations.

        Arguments
        ----------
        param    : class, parameters related to the surface we are studying.

        """

        self.N = len(self.triangle)
        self.Nj = self.N * param.K
        # Calculate centers
        self.calc_centers()

        self.calc_norms()
        # Set Gauss points (sources)
        self.get_gauss_points(param.K)

        # Calculate distances, get R_C0
        self.calc_distance(param)

        # Generate tree, compute indices and precompute terms for M2M
        self.tree = generateTree(self.xi, self.yi, self.zi, param.NCRIT, param.Nm,
                                 self.N, self.R_C0, self.x_center)
        C = 0
        self.twig = findTwigs(self.tree, C, self.twig, param.NCRIT)

        addSources(self.tree, self.twig, param.K)

        self.xk, self.wk = GQ_1D(param.Nk)
        self.Xsk, self.Wsk = quadratureRule_fine(param.K_fine)

        self.generate_preconditioner()

        tic = time.time()
        sortPoints(self, self.tree, self.twig, param)
        toc = time.time()
        time_sort = toc - tic

        return time_sort

    def calc_centers(self):
        self.xi = numpy.average(self.vertex[self.triangle[:], 0], axis=1)
        self.yi = numpy.average(self.vertex[self.triangle[:], 1], axis=1)
        self.zi = numpy.average(self.vertex[self.triangle[:], 2], axis=1)

    def calc_norms(self):

        L0 = self.vertex[self.triangle[:, 1]] - self.vertex[self.triangle[:, 0]]
        L2 = self.vertex[self.triangle[:, 0]] - self.vertex[self.triangle[:, 2]]

        self.normal = numpy.cross(L0, L2)
        self.Area = numpy.sqrt(numpy.sum(self.normal**2, axis=1)) / 2
        self.normal /= (2 * self.Area[:, numpy.newaxis])

    def calc_distance(self, param):

        self.x_center = numpy.average(numpy.vstack((self.xi,
                                                   self.yi,
                                                   self.zi)), axis=1).astype(param.REAL)
        dist = numpy.sqrt((self.xi - self.x_center[0])**2 +
                          (self.yi - self.x_center[1])**2 +
                          (self.zi - self.x_center[2])**2)
        self.R_C0 = max(dist)

    def get_gauss_points(self, n):
        """
        It gets the Gauss points for far away integrals.

        Arguments
        ----------
        y       : list, vertices of the triangles.
        triangle: list, indices for the corresponding triangles.
        n       : int (1,3,4,7), desired Gauss points per element.

        Returns
        --------
        xi[:,0] : position of the gauss point in the x axis.
        xi[:,1] : position of the gauss point in the y axis.
        xi[:,2] : position of the gauss point in the z axis.
        """

        #N  = len(triangle) # Number of triangles
        gauss_array = numpy.zeros((self.N*n,3))
        if n==1:
            gauss_array = numpy.average(self.vertex[self.triangle], axis=1)

        elif n==3:
            for i in range(self.N):
                M = self.vertex[self.triangle[i]]
                gauss_array[n*i, :] = numpy.dot(M.T, numpy.array([0.5, 0.5, 0.]))
                gauss_array[n*i+1, :] = numpy.dot(M.T, numpy.array([0., 0.5, 0.5]))
                gauss_array[n*i+2, :] = numpy.dot(M.T, numpy.array([0.5, 0., 0.5]))

        elif n==4:
            for i in range(self.N):
                M = self.vertex[self.triangle[i]]
                gauss_array[n*i, :] = numpy.dot(M.T, numpy.array([1/3., 1/3., 1/3.]))
                gauss_array[n*i+1, :] = numpy.dot(M.T, numpy.array([3/5., 1/5., 1/5.]))
                gauss_array[n*i+2, :] = numpy.dot(M.T, numpy.array([1/5., 3/5., 1/5.]))
                gauss_array[n*i+3, :] = numpy.dot(M.T, numpy.array([1/5., 1/5., 3/5.]))

        elif n==7:
            for i in range(self.N):
                M = self.vertex[self.triangle[i]]
                gauss_array[n*i+0, :] = numpy.dot(M.T, numpy.array([1/3.,1/3.,1/3.]))
                gauss_array[n*i+1, :] = numpy.dot(M.T, numpy.array([.797426985353087, .101286507323456, .101286507323456]))
                gauss_array[n*i+2, :] = numpy.dot(M.T, numpy.array([.101286507323456, .797426985353087, .101286507323456]))
                gauss_array[n*i+3, :] = numpy.dot(M.T, numpy.array([.101286507323456, .101286507323456, .797426985353087]))
                gauss_array[n*i+4, :] = numpy.dot(M.T, numpy.array([.059715871789770, .470142064105115, .470142064105115]))
                gauss_array[n*i+5, :] = numpy.dot(M.T, numpy.array([.470142064105115, .059715871789770, .470142064105115]))
                gauss_array[n*i+6, :] = numpy.dot(M.T, numpy.array([.470142064105115, .470142064105115, .059715871789770]))

        self.xj, self.yj, self.zj = gauss_array.T


    def generate_preconditioner(self):
        # Generate preconditioner
        # Will use block-diagonal preconditioner (AltmanBardhanWhiteTidor2008)
        # If we have complex dielectric constants we need to initialize Precon with
        # complex type else it'll be float.
        if type(self.E_hat) == complex:
            self.Precond = numpy.zeros((4, self.N), complex)
        else:
            self.Precond = numpy.zeros((4, self.N))
        # Stores the inverse of the block diagonal (also a tridiag matrix)
        # Order: Top left, top right, bott left, bott right
        centers = numpy.vstack((self.xi, self.yi, self.zi)).T

        #   Compute diagonal integral for internal equation
        VL = numpy.zeros(self.N)
        KL = numpy.zeros(self.N)
        VY = numpy.zeros(self.N)
        KY = numpy.zeros(self.N)
        computeDiagonal(VL, KL, VY, KY, numpy.ravel(self.vertex[self.triangle[:]]),
                        numpy.ravel(centers), self.kappa_in, 2 * numpy.pi, 0.,
                        self.xk, self.wk)
        if self.LorY_in == 1:
            dX11 = KL
            dX12 = -VL
            self.sglInt_int = VL  # Array for singular integral of V through interior
        elif self.LorY_in == 2:
            dX11 = KY
            dX12 = -VY
            self.sglInt_int = VY  # Array for singular integral of V through interior
        else:
            self.sglInt_int = numpy.zeros(self.N)

    #   Compute diagonal integral for external equation
        VL = numpy.zeros(self.N)
        KL = numpy.zeros(self.N)
        VY = numpy.zeros(self.N)
        KY = numpy.zeros(self.N)
        computeDiagonal(VL, KL, VY, KY, numpy.ravel(self.vertex[self.triangle[:]]),
                        numpy.ravel(centers), self.kappa_out, 2 * numpy.pi, 0.,
                        self.xk, self.wk)
        if self.LorY_out == 1:
            dX21 = KL
            dX22 = self.E_hat * VL
            self.sglInt_ext = VL  # Array for singular integral of V through exterior
        elif self.LorY_out == 2:
            dX21 = KY
            dX22 = self.E_hat * VY
            self.sglInt_ext = VY  # Array for singular integral of V through exterior
        else:
            self.sglInt_ext = numpy.zeros(N)

        if self.surf_type != 'dirichlet_surface' and self.surf_type != 'neumann_surface':
            d_aux = 1 / (dX22 - dX21 * dX12 / dX11)
            self.Precond[0, :] = 1 / dX11 + 1 / dX11 * dX12 * d_aux * dX21 / dX11
            self.Precond[1, :] = -1 / dX11 * dX12 * d_aux
            self.Precond[2, :] = -d_aux * dX21 / dX11
            self.Precond[3, :] = d_aux
        elif self.surf_type == 'dirichlet_surface':
            self.Precond[0, :] = 1 / VY  # So far only for Yukawa outside
        elif self.surf_type == 'neumann_surface' or self.surf_type == 'asc_surface':
            self.Precond[0, :] = 1 / (2 * numpy.pi)

class Field():
    """
    Field class.
    It contains the information about each region in the molecule.

    Attributes
    -----------

    parent: list, Pointer to "parent" surface.
    child : list, Pointer to "children" surfaces.
    LorY  : int, 1: Laplace, 2: Yukawa.
    kappa : float, inverse of Debye length.
    E     : float, dielectric constant.
    xq    : list, position of charges.
    q     : list, value of charges.
    coul  : int, 1: perform Coulomb interaction calculation, 0: don't do Coulomb.

    # Device data

    xq_gpu: list, x position of charges on GPU.
    yq_gpu: list, y position of charges on GPU.
    zq_gpu: list, z position of charges on GPU.
    q_gpu : list, value of charges on GPU.
    """

    def __init__(self):
        self.parent = []    # Pointer to "parent" surface
        self.child  = []    # Pointer to "children" surfaces
        self.LorY   = []    # 1: Laplace, 2: Yukawa
        self.kappa  = []    # inverse of Debye length
        self.E      = []    # dielectric constant
        self.xq     = []    # position of charges
        self.q      = []    # value of charges
        self.coul   = []    # 1: perform Coulomb interaction calculation
                            # 0: don't do Coulomb calculation

        # Device data
        self.xq_gpu = []    # x position of charges on gpu
        self.yq_gpu = []    # y position of charges on gpu
        self.zq_gpu = []    # z position of charges on gpu
        self.q_gpu  = []    # value of charges on gpu


class Timing():
    """
    Timing class.
    It contains timing information for different parts of the code.

    Attributes
    -----------
    time_an   : float, time spent in compute the near singular integrals.
    time_P2P  : float, time spent in compute the P2P part of the treecode.
    time_P2M  : float, time spent in compute the P2M part of the treecode.
    time_M2M  : float, time spent in compute the M2M part of the treecode.
    time_M2P  : float, time spent in compute the M2P part of the treecode.
    time_trans: float, time spent in transfer data to and from the GPU.
    time_sort : float, time spent in sorting data to send to the GPU.
    time_mass : float, time spent in compute the mass of the sources in treecode.
    AI_int    : int, counter of the amount of near singular integrals solved.
    """

    def __init__(self):
        self.time_an    = 0.
        self.time_P2P   = 0.
        self.time_P2M   = 0.
        self.time_M2M   = 0.
        self.time_M2P   = 0.
        self.time_trans = 0.
        self.time_sort  = 0.
        self.time_mass  = 0.
        self.AI_int     = 0


class Parameters():
    """
    Parameters class.
    It contains the information of the parameters needed to run the code.

    Attributes
    -----------

    kappa        :  float, inverse of Debye length.
    restart      :  int, Restart of GMRES.
    tol          :  float, Tolerance of GMRES.
    max_iter     :  int, Max number of GMRES iterations.
    P            :  int, Order of Taylor expansion.
    eps          :  int, Epsilon machine.
    Nm           :  int, Number of terms in Taylor expansion.
    NCRIT        :  int, Max number of targets per twig box.
    theta        :  float, MAC criterion for treecode.
    K            :  int, Number of Gauss points per element.
    K_fine       :  int, Number of Gauss points per element for near singular integrals.
    threshold    :  float, L/d criterion for semi-analytic intergrals.
    Nk           :  int, Gauss points per side for semi-analytical integrals.
    BSZ          :  int, CUDA block size.
    Nround       :  int, Max size of sorted target array.
    BlocksPerTwig:  int, Number of CUDA blocks that fit per tree twig.
    N            :  int, Total number of elements.
    Neq          :  int, Total number of equations.
    qe           :  float, Charge of an electron (1.60217646e-19).
    Na           :  float, Avogadro's number (6.0221415e23).
    E_0          :  float, Vacuum dielectric constant (8.854187818e-12).
    REAL         :  Data type.
    E_field      :  list, Regions where energy will be calculated.
    GPU          :  int, =1: with GPU, =0: no GPU.
    """

    def __init__(self):
        self.kappa         = 0.              # inverse of Debye length
        self.restart       = 0               # Restart of GMRES
        self.tol           = 0.              # Tolerance of GMRES
        self.max_iter      = 0               # Max number of GMRES iterations
        self.P             = 0               # Order of Taylor expansion
        self.eps           = 0               # Epsilon machine
        self.Nm            = 0               # Number of terms in Taylor expansion
        self.NCRIT         = 0               # Max number of targets per twig box
        self.theta         = 0.              # MAC criterion for treecode
        self.K             = 0               # Number of Gauss points per element
        self.K_fine        = 0               # Number of Gauss points per element for near singular integrals
        self.threshold     = 0.              # L/d criterion for semi-analytic intergrals
        self.Nk            = 0               # Gauss points per side for semi-analytical integrals
        self.BSZ           = 0               # CUDA block size
        self.Nround        = 0               # Max size of sorted target array
        self.BlocksPerTwig = 0               # Number of CUDA blocks that fit per tree twig
        self.N             = 0               # Total number of elements
        self.Neq           = 0               # Total number of equations
        self.qe            = 1.60217646e-19  # Charge of an electron
        self.Na            = 6.0221415e23    # Avogadro's number
        self.E_0           = 8.854187818e-12 # Vacuum dielectric constant
        self.REAL          = 0               # Data type
        self.E_field       = []              # Regions where energy will be calculated
        self.GPU           = -1              # =1: with GPU, =0: no GPU


class IndexConstant():
    """
    It contains the precompute indices required for the treecode computation.

    Attributes
    -----------

    II         : list, multipole order in the x-direction for the treecode.
    JJ         : list, multipole order in the y-direction for the treecode.
    KK         : list, multipole order in the z-direction for the treecode.
    index_large: list, pointers to the position of multipole order i, j, k
                       in the multipole array, organized in a 1D array of size
                       P*P*P. Index is given by index[i*P*P+j*P+k]
    index_small: list, pointers to the position of multipole order i, j, k
                       in the multipole array, organized in a 1D array which is
                       compressed with respect to index_large (does not consider
                       combinations of i,j,k which do not have a multipole).
    index      : list, copy of index_small
    index_ptr  : list, pointer to index_small. Data in index_small is organized
                      in a i-major fashion (i,j,k), and index_ptr points at the
                      position in index_small where the order i changes.
    combII     : array, combinatory of (I, i) where I is the maximum i multipole.
                       Used in coefficients of M2M.
    combJJ     : array, combinatory of (J, j) where J is the maximum j multipole.
                       Used in coefficients of M2M.
    combKK     : array, combinatory of (K, k) where K is the maximum k multipole.
                       Used in coefficients of M2M.
    IImii      : array, I-i where I is the maximum i multipole.
                       Used in exponents of M2M.
    JJmjj      : array, J-j where J is the maximum j multipole.
                       Used in exponents of M2M.
    KKmkk      : array, K-k where K is the maximum k multipole.
                       Used in exponents of M2M.

    # Device data

    indexDev   : list, index_large on GPU.
    """

    def __init__(self):
        self.II = []
        self.JJ = []
        self.KK = []
        self.index       = []
        self.index_small = []
        self.index_large = []
        self.index_ptr   = []
        self.combII = []
        self.combJJ = []
        self.combKK = []
        self.IImii  = []
        self.JJmjj  = []
        self.KKmkk  = []

        # Device data
        self.indexDev = []
