import os
import surfex
import shutil
import numpy as np
from datetime import timedelta, datetime
from netCDF4 import Dataset, num2date, chartostring
import re
import abc
import pyproj


class SurfexIO(object):
    def __init__(self, filename, file_format, geo, input_file=None, symlink=True, archive_file=None):
        self.format = file_format
        self.filename = filename + self.format.extension
        self.geo = geo
        self.input_file = input_file
        self.symlink = symlink
        if self.input_file is not None:
            if self.symlink:
                self.symlink_input()
            else:
                self.copy_input()
        self.archive_file = archive_file

    def symlink_input(self):
        if self.input_file is not None:
            f_out = os.getcwd() + "/" + self.filename
            surfex.read.remove_existing_file(self.input_file, f_out)
            if os.path.abspath(self.input_file) != f_out:
                print("Symlink " + self.input_file + " -> " + f_out)
                os.symlink(self.input_file, f_out)

    def copy_input(self):
        if self.input_file is not None:
            f_out = os.getcwd() + "/" + self.filename
            surfex.read.remove_existing_file(self.input_file, f_out)
            if os.path.abspath(self.input_file) != f_out:
                print("Copy " + self.input_file + " -> " + f_out)
                shutil.copy2(self.input_file, f_out)

    def archive_output_file(self):
        if self.archive_file is not None:
            dirname = os.path.dirname(os.path.abspath(self.archive_file))
            os.makedirs(dirname, exist_ok=True)
            f_in = os.getcwd() + "/" + self.filename
            if os.path.abspath(self.archive_file) != f_in:
                print("Move " + f_in + " to " + self.archive_file)
                if os.path.islink(self.archive_file):
                    # print("is link")
                    os.unlink(self.archive_file)
                if os.path.isfile(self.archive_file):
                    # print("is file")
                    os.remove(self.archive_file)
                if os.path.isdir(self.archive_file):
                    shutil.rmtree(self.archive_file)
                shutil.move(f_in, self.archive_file)


class PGDFile(SurfexIO):
    def __init__(self, csurf_filetype, cpgdfile, geo, input_file=None, symlink=True, archive_file=None, lfagmap=True):
        self.csurf_filetype = csurf_filetype
        self.cpgdfile = cpgdfile
        self.need_pgd = False
        if self.csurf_filetype.upper() == "NC":
            file_format = surfex.NC()
        elif self.csurf_filetype.upper() == "FA":
            file_format = surfex.FA(lfagmap=lfagmap)
        elif self.csurf_filetype.upper() == "ASCII":
            file_format = surfex.ASCII()
        else:
            raise NotImplementedError

        SurfexIO.__init__(self, self.cpgdfile, file_format, geo, input_file=input_file,
                          archive_file=archive_file, symlink=symlink)


class PREPFile(SurfexIO):
    def __init__(self, csurf_filetype, cprepfile, geo, input_file=None, symlink=True, archive_file=None, lfagmap=True):
        self.csurf_filetype = csurf_filetype
        self.cprepfile = cprepfile
        self.need_pgd = True
        print(self.csurf_filetype)
        if self.csurf_filetype.upper() == "NC":
            file_format = surfex.NC()
        elif self.csurf_filetype.upper() == "FA":
            file_format = surfex.FA(lfagmap=lfagmap)
        elif self.csurf_filetype.upper() == "ASCII":
            file_format = surfex.ASCII()
        else:
            raise NotImplementedError

        SurfexIO.__init__(self, self.cprepfile, file_format, geo, input_file=input_file,
                          archive_file=archive_file, symlink=symlink)


class SURFFile(SurfexIO):
    def __init__(self, csurf_filetype, csurfile, geo, archive_file=None, lfagmap=True, input_file=None):
        self.csurf_filetype = csurf_filetype
        self.csurfile = csurfile
        self.need_pgd = True
        if self.csurf_filetype.upper() == "NC":
            fileformat = surfex.NC()
        elif self.csurf_filetype.upper() == "FA":
            fileformat = surfex.FA(lfagmap=lfagmap)
        elif self.csurf_filetype.upper() == "ASCII":
            fileformat = surfex.ASCII()
        else:
            raise NotImplementedError

        SurfexIO.__init__(self, self.csurfile, fileformat, geo, input_file=input_file,
                          archive_file=archive_file)


class SurfexFileVariable(object):
    """
    Surfex Variable
    """

    def __init__(self, varname, validtime=None, patches=1, layers=1, basetime=None, interval=None, datatype="float"):
        self.varname = varname
        self.type = datatype
        self.patches = patches
        self.layers = layers
        self.basetime = basetime
        self.interval = interval
        self.validtime = validtime


def get_surfex_io_object(fname, filetype="surf", fileformat=None, geo=None):

    if filetype is not None:
        if filetype.lower() != "surf" and filetype.lower() != "ts" and filetype.lower() != "forcing":
            raise Exception("Invalid filetype: " + filetype + " Allowed: surf/ts/forcing")

    if fileformat is None:
        fileformat, filetype = guess_file_format(fname, filetype)

    if fileformat.lower() == "ascii":
        if filetype.lower() == "surf":
            obj = AsciiSurfexFile(fname)
        elif filetype.lower() == "forcing":
            raise NotImplementedError("Not implemented yet")
        else:
            raise NotImplementedError

    elif fileformat.lower() == "netcdf":
        if filetype.lower() == "surf":
            obj = NCSurfexFile(fname)
        elif filetype == "ts":
            if geo is None:
                raise Exception("Format NetCDF needs a geometry")
            obj = NetCDFSurfexFile(geo, fname)
        elif filetype.lower() == "forcing":
            if geo is None:
                raise Exception("Format NetCDF needs a geometry for reading forcing files")
            obj = ForcingFileNetCDF(fname, geo)
        else:
            raise NotImplementedError
    elif fileformat.lower() == "texte":
        if geo is None:
            raise Exception("Format TEXTE needs a geometry")
        obj = TexteSurfexFile(geo, fname)
    else:
        raise NotImplementedError("Format not implemented: " + fileformat)

    return obj


def guess_file_format(fname, ftype=None):

    fn = str(os.path.basename(fname))
    ext = str(fn.split(".")[-1])
    if ftype is None:
        surfex.util.info("Trying to guess the file type")
        needles = ["PREP", "PGD"]
        for needle in range(0, len(needles)):
            if re.search(needles[needle], fn):
                ftype = "surf"

        if ext.endswith("nc"):
            ftype = "surf"
        needles = [".*PROGNOSTIC.*", ".*DIAGNOSTICS.*", "SURF_ATM.*"]
        for needle in range(0, len(needles)):
            if re.search(needles[needle], fn):
                ftype = "ts"
        for needle in range(0, len(needles)):
            if ext.endswith("TXT"):
                ftype = "ts"
        needles = ["Forc_.*", "FORCING.*"]
        for needle in range(0, len(needles)):
            if re.search(needles[needle], fn):
                ftype = "forcing"

        if re.search("SURFOUT.*", fn) and ftype is None:
            raise Exception("Can not-auto decide filetype for files called SURFOUT.*.txt. " +
                            "Specify either surf or ts")

    fileformat = None
    surfex.util.info("Trying to guess the file format from extension: " + ext)
    if ext.endswith("txt"):
        fileformat = "ascii"
    if ext.endswith("TXT"):
        fileformat = "texte"
    if ext.endswith("nc"):
        fileformat = "netcdf"
    if ext.endswith("fa"):
        fileformat = "fa"
    if ext.endswith("sfx"):
        fileformat = "fa"

    if ftype is None or fileformat is None:
        raise Exception("Filetype and/or format not set: " + str(ftype) + " & " + str(fileformat))
    surfex.util.info("Filetype: " + ftype + " format: " + fileformat)

    return fileformat, ftype


########################################################################################################################
class SurfexFile(object):
    """
           Abstract base class for a surfex file
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, fname, geo):
        if not os.path.isfile(fname):
            raise FileNotFoundError("File does not exist: " + fname)
        self.fname = fname
        self.geo = geo
        self.nearest = None
        self.linear = None
        print("Constructed SurfFile")

    @abc.abstractmethod
    def field(self, var, validtime=None):
        raise NotImplementedError("This method is not implemented for this class!")

    @abc.abstractmethod
    def points(self, var, geo_out, validtime=None, interpolation="nearest", cache=None):
        raise NotImplementedError("This method is not implemented for this class!")

    def interpolate_field(self, field, geo_in, geo_out, interpolation="nearest", cache=None):

        if interpolation == "nearest":
            surfex.util.info("Nearest neighbour", level=2)
            interpolator = surfex.interpolation.NearestNeighbour(geo_in, geo_out, cache=cache)
        elif interpolation == "linear":
            surfex.util.info("Linear interpolation", level=2)
            interpolator = surfex.interpolation.Linear(geo_in, geo_out, cache=cache)
        elif interpolation == "none":
            surfex.util.info("No interpolation", level=2)
            interpolator = surfex.interpolation.NoInterpolation(geo_in, geo_out, cache=cache)
        else:
            raise NotImplementedError("Interpolation type " + interpolation + " not implemented!")

        field = interpolator.interpolate(field)
        return field, interpolator


class AsciiSurfexFile(SurfexFile):

    def __init__(self, fname):
        if not os.path.isfile(self.fname):
            raise FileNotFoundError("File does not exist: " + str(fname))

        grid = self.read("GRID_TYPE", "FULL", "string")
        if len(grid) == 0:
            raise Exception("No grid found")

        if grid[0] == "IGN":
            domain = {
                "nam_ign": {
                    "clambert": self.read("LAMBERT", "&FULL", "integer")[0],
                    "xx": self.read("XX", "&FULL", "float"),
                    "xy": self.read("XY", "&FULL", "float"),
                    "xdx": self.read("XDX", "&FULL", "float"),
                    "xdy": self.read("XY", "&FULL", "float")
                }
            }
            geo = surfex.geo.IGN(domain)

        elif grid[0] == "LONLATVAL":
            domain = {
                "nam_lonlatval": {
                    "xx": self.read("XX", "&FULL", "float"),
                    "xy": self.read("XY", "&FULL", "float"),
                    "xdx": self.read("DX", "&FULL", "float"),
                    "xdy": self.read("DY", "&FULL", "float")
                }
            }
            geo = surfex.geo.LonLatVal(domain)

        elif grid[0] == "LONLAT REG":
            domain = {
                "nam_lonlatval_reg": {
                    "lonmin": self.read("LONMIN", "&FULL", "float")[0],
                    "latmin": self.read("LATMIN", "&FULL", "float")[0],
                    "lonmax": self.read("LONMAX", "&FULL", "float")[0],
                    "latmax": self.read("LATMAX", "&FULL", "float")[0],
                    "nlon": self.read("NLON", "&FULL", "integer")[0],
                    "nlat": self.read("NLAT", "&FULL", "integer")[0],
                    "reg_lon": self.read("REG_LON", "&FULL", "float")[0],
                    "reg_lat": self.read("REG_LAT", "&FULL", "float")[0]
                }
            }
            geo = surfex.geo.LonLatReg(domain)

        elif grid[0] == "CONF PROJ":
            domain = {
                "nam_conf_proj": {
                    "lon0": self.read("LON0", "&FULL", "float")[0],
                    "lat0": self.read("LAT0", "&FULL", "float")[0]
                },
                "nam_conf_proj_grid": {
                    "xloncen": self.read("LONORI", "&FULL", "float")[0],
                    "xlatcen": self.read("LATORI", "&FULL", "float")[0],
                    "nimax": self.read("IMAX", "&FULL", "integer")[0],
                    "njmax": self.read("JMAX", "&FULL", "integer")[0],
                    "xdx": self.read("XX", "&FULL", "float"),
                    "xdy": self.read("YY", "&FULL", "float")
                }
            }
            geo = surfex.geo.ConfProj(domain)

        else:
            raise NotImplementedError("Grid " + str(grid[0]) + " not implemented!")

        # Surfex version
        self.version = self.read("VERSION", "&FULL", "integer")[0]
        self.bug = self.read("BUG", "&FULL", "integer")[0]
        SurfexFile.__init__(self, fname, geo)

    def read(self, read_par, read_tile, datatype):

        # Add & if not given
        if read_tile.find('&') < 0:
            read_tile = '&' + read_tile
        # print read_tile,read_par
        file = open(self.fname, mode="r")
        read_desc = False
        read_value = False
        values = []
        for line in file:
            # for line in file.read().splitlines():

            # print "T:"+line
            words = line.split()
            if len(words) > 0:
                # print "Line:",read_desc,read_value,":",line
                if read_value and not read_desc:
                    if words[0].find('&') < 0:
                        # print "Value:", line
                        try:
                            if datatype.lower() == "float":
                                for i in range(0, len(words)):
                                    val = float(words[i].replace("D", "E"))
                                    if val == 1e+20:
                                        val = np.nan
                                    values.append(val)
                            elif datatype.lower() == "string":
                                str_words = []
                                for i in range(0, len(words)):
                                    str_words.append(words[i])
                                values.append(" ".join(str_words))
                            elif datatype.lower() == "integer" or datatype.lower() == "int":
                                for i in range(0, len(words)):
                                    values.append(int(words[i]))
                            else:
                                raise NotImplementedError("Type not implemented " + str(datatype))
                        except ValueError:
                            raise Exception('Conversion from ' + str(words) + " to " + str(datatype) +
                                            " does not work! Try a different datatype!")

                if read_desc:
                    # print "Description: ", words[0]
                    read_desc = False
                    read_value = True

                if words[0].find('&') >= 0:
                    tile = words[0]
                    par = words[1]

                    read_value = False
                    if tile.strip().lower() == read_tile.lower() and par.lower() == read_par.lower():
                        read_desc = True
                        read_value = False
                        print("Found:" + str(tile) + " " + str(par))

            # Description could be empty
            else:
                if read_desc:
                    # print "Description: ", words[0]
                    read_desc = False
                    read_value = True

        if len(values) == 0:
            print("No values found!")

        values = np.asarray(values)
        return values

    def field(self, var, validtime=None):
        raise NotImplementedError("TODO: Not implemented yet")

    def points(self, var, geo_out, validtime=None, interpolation="nearest", cache=None):
        raise NotImplementedError("TODO: Not implemented yet")


class NCSurfexFile(SurfexFile):

    def __init__(self, filename):
        self.filename = filename
        self.fh = Dataset(filename, "r")

        cgrid = str(chartostring(self.fh["GRID_TYPE"][:])).strip()
        print(":" + cgrid + ":")
        if cgrid == "CONF PROJ":
            lon0 = self.fh["LON0"][:]
            lat0 = self.fh["LAT0"][:]
            nx = int(self.fh["IMAX"][0])
            ny = int(self.fh["JMAX"][0])
            dx = float(self.fh["DX"][0][0])
            dy = float(self.fh["DY"][0][0])

            ll_lon = self.fh["LONORI"][:]
            ll_lat = self.fh["LATORI"][:]
            earth = 6.37122e+6
            proj4 = "+proj=lcc +lat_0=" + str(lat0) + " +lon_0=" + str(lon0) + " +lat_1=" + \
                    str(lat0) + " +lat_2=" + str(lat0) + " +units=m +no_defs +R=" + str(earth)

            proj = pyproj.Proj(proj4)
            x0, y0 = proj(ll_lon, ll_lat)
            xc = x0 + 0.5 * (nx - 1) * dx
            yc = y0 + 0.5 * (ny - 1) * dy
            lonc, latc = proj(xc, yc, inverse=True)

            domain = {
                "nam_conf_proj": {
                    "xlon0": self.fh["LON0"][0],
                    "xlat0": self.fh["LAT0"][0],
                    "xrpk": self.fh["RPK"][0],
                    "beta": self.fh["BETA"][0]
                },
                "nam_conf_proj_grid": {
                    "xloncen": lonc,
                    "xlatcen": latc,
                    "nimax": nx,
                    "njmax": ny,
                    "xdx": dx,
                    "xdy": dy,
                    "ilone": 0,
                    "ilate": 0
                }
            }
            geo = surfex.geo.ConfProj(domain)
        elif cgrid == "IGN":
            domain = {
                "nam_ign": {
                    "clambert": self.fh["CLAMBERT"][0],
                    "xx": self.fh["XX"][:],
                    "xy": self.fh["XY"][:],
                    "xdx": self.fh["DX"][:],
                    "xdy": self.fh["DY"][:]
                }
            }
            geo = surfex.geo.IGN(domain)

        elif cgrid == "LONLATVAL":
            domain = {
                "nam_lonlatval": {
                    "xx": self.fh["XX"][:],
                    "xy": self.fh["XY"][:],
                    "xdx": self.fh["DX"][:],
                    "xdy": self.fh["DY"][:]
                }
            }
            geo = surfex.geo.LonLatVal(domain)

        elif cgrid == "LONLAT REG":
            domain = {
                "nam_lonlatval_reg": {
                    "lonmin": self.fh["LONMIN"][0],
                    "latmin": self.fh["LATMIN"][0],
                    "lonmax": self.fh["LONMAX"][0],
                    "latmax": self.fh["LATMAX"][0],
                    "nlon": self.fh["NLON"][0],
                    "nlat": self.fh["NLAT"][0],
                    "reg_lon": self.fh["REG_LON"][0],
                    "reg_lat": self.fh["REG_LAT"][0],
                }
            }
            geo = surfex.geo.LonLatReg(domain)
        else:
            raise NotImplementedError(cgrid + " is not implemented")

        SurfexFile.__init__(self, filename, geo)

    def field(self, var, validtime=None):

        if validtime is None:
            pass
        elif type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        else:
            if hasattr(self.fh, "DTCUR-YEAR"):
                year = self.fh["DTCUR-YEAR"][0]
                month = self.fh["DTCUR-MONTH"][0]
                day = self.fh["DTCUR-DAY"][0]
                time = int(self.fh["DTCUR-TIME"][0])
                hour = int(time/3600)

                # TODO minutes
                time_in_file = datetime(year=year, month=month, day=day, hour=hour)
                if validtime != time_in_file:
                    print(time_in_file, validtime)
                    raise Exception("Mismatch in times in file and the wanted time")
            else:
                print("Not checking time")

        geo_in = self.geo
        field = self.fh[var.varname][:]
        # Reshape to fortran 2D style

        field = np.reshape(field, [geo_in.nlons, geo_in.nlats], order="F")
        field = np.transpose(field)
        return field, geo_in

    def points(self, var, geo_out, validtime=None, interpolation="nearest", cache=None):

        if validtime is not None and type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        field, geo_in = self.field(var, validtime=validtime)

        points, interpolator = SurfexFile.interpolate_field(self, field, geo_in, geo_out, interpolation=interpolation,
                                                            cache=cache)
        return points, interpolator


class FaSurfexFile(SurfexFile):

    def __init__(self, filename, geo):
        self.fh = surfex.fa.Fa(filename)

        SurfexFile.__init__(self, filename, geo)

    def field(self, var, validtime=None):
        if validtime is None:
            pass
        elif type(validtime) != datetime:
            raise Exception("validime must be a datetime object")

        geo_in = self.geo
        field = self.fh.field(var.varname, validtime)

        # Reshape to fortran 2D style
        field = np.reshape(field, [geo_in.nlons, geo_in.nlats], order="F")
        field = np.transpose(field)
        return field, geo_in

    def points(self, var, geo_out, validtime=None, interpolation="nearest", cache=None):

        if validtime is not None and type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        field, geo_in = self.field(var, validtime=validtime)

        points, interpolator = SurfexFile.interpolate_field(self, field, geo_in, geo_out, interpolation=interpolation,
                                                            cache=cache)
        return points, interpolator


class NetCDFSurfexFile(SurfexFile):
    """
    Reading surfex NetCDF output
    """

    def __init__(self, geo, filename):
        SurfexFile.__init__(self, filename, geo)
        self.fh = Dataset(filename, "r")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fh.close()

    def read(self, var, times):
        """

        Read a field, return a 2D array
        :param var:
        :param times:
        :return: values, geo
        """

        layers = var.layers
        patches = var.patches

        if not isinstance(times, (list, tuple)):
            raise Exception("times must be list or tuple")
        if not isinstance(layers, (list, tuple)):
            raise Exception("patches must be list or tuple")
        if not isinstance(patches, (list, tuple)):
            raise Exception("patches must be list or tuple")

        values = np.array([])
        times_read = []
        ndims = 0
        dim_indices = []
        mapping = {}
        npatch = 1

        if self.fh.variables[var].shape[0] > 0:
            # p rint self.fh.variables[var]
            for dim in self.fh.variables[var].dimensions:
                # print dim,ndims
                dimlen = self.fh.variables[var].shape[ndims]
                this_dim = []

                if dim == "time":
                    mapping[0] = ndims
                    times_for_var = self.fh.variables['time']
                    units = times_for_var.units
                    try:
                        t_cal = times_for_var.calendar
                    except AttributeError:  # Attribute doesn't exist
                        t_cal = u"gregorian"  # or standard

                    indices = []
                    [indices.append(i) for i in range(0, dimlen)]
                    times_for_var = num2date(times_for_var[indices], units=units, calendar=t_cal)
                    if len(times) > 0:
                        for t_to_find in range(0, len(times)):
                            for t in range(0, len(indices)):
                                if times_for_var[t] == times[t_to_find]:
                                    # print t, t_to_find, times_for_var[t], times[t_to_find]
                                    this_dim.append(t)
                                    times_read.append(times[t_to_find])
                    else:
                        times_read = times_for_var
                        [this_dim.append(i) for i in range(0, dimlen)]

                elif dim == "Number_of_points":
                    mapping[1] = ndims
                    [this_dim.append(i) for i in range(0, dimlen)]
                elif dim == "xx":
                    mapping[1] = ndims
                    [this_dim.append(i) for i in range(0, dimlen)]
                elif dim == "yy":
                    mapping[2] = ndims
                    [this_dim.append(i) for i in range(0, dimlen)]
                elif dim == "Number_of_Tile":
                    mapping[3] = ndims
                    npatch = dimlen
                    if len(patches) > 0:
                        npatch = len(patches)
                        this_dim = patches
                    else:
                        [this_dim.append(i) for i in range(0, dimlen)]
                elif dim == "Number_of_Layers":
                    mapping[4] = ndims
                    npatch = dimlen
                    if len(layers) > 0:
                        # nlayers = len(layers)
                        this_dim = layers
                    else:
                        [this_dim.append(i) for i in range(0, dimlen)]
                elif dim == "lon":
                    mapping[1] = ndims
                    [this_dim.append(i) for i in range(0, dimlen)]
                elif dim == "lat":
                    mapping[2] = ndims
                    [this_dim.append(i) for i in range(0, dimlen)]
                else:
                    raise NotImplementedError("Not implemented for: " + dim)

                dim_indices.append(this_dim)
                ndims = ndims + 1

            field = self.fh.variables[var][dim_indices]

            # Add extra dimensions
            # print mapping
            i = 0
            reverse_mapping = []
            for d in range(0, 5):
                if d not in mapping:
                    # print "Adding dimension " + str(d)
                    field = np.expand_dims(field, len(dim_indices) + i)
                    reverse_mapping.append(len(dim_indices) + i)
                    i = i + 1
                else:
                    reverse_mapping.append(mapping[d])

            # Transpose to 5D array
            # print "Transpose to 5D array"
            # print reverse_mapping
            field = np.transpose(field, reverse_mapping)
            npoints = self.geo.npoints * npatch

            # Create 2-D array with times and points as for the other formats
            for t in range(0, field.shape[0]):
                field2d = np.empty(npoints)
                i = 0
                # print t,npatch,npoints,field.shape,field2d.shape
                for p in range(0, npatch):
                    if self.geo.mask is not None:
                        ii = 0
                        j = 0
                        # For some reason the NetCDF files have one less dimension in all
                        # dimensions than the PGD dimension and mask needs x first.
                        for x in range(-1, field.shape[1] + 1):
                            for y in range(-1, field.shape[2] + 1):
                                if x in range(0, field.shape[1]) and y in range(0, field.shape[2]):
                                    # print i, ii,j, t, x, y, p, self.geo.mask[j]
                                    if self.geo.mask[j] == ii:
                                        field2d[i] = np.nan
                                        if field[t, x, y, p] != np.nan:
                                            field2d[i] = field[t, x, y, p]
                                        i = i + 1
                                        j = j + 1
                                ii = ii + 1
                    else:
                        for y in range(0, field.shape[2]):
                            for x in range(0, field.shape[1]):
                                field2d[i] = np.nan
                                if field[t, x, y, p] != np.nan:
                                    field2d[i] = field[t, x, y, p]
                                i = i + 1
                if i != npoints:
                    raise Exception("Mismatch in points " + str(i) + "!=" + str(npoints))

                values = np.append(values, field2d)
            # Re-shape to proper format
            values = np.reshape(values, [field.shape[0], npoints])

        else:
            raise Exception("Variable " + var + " not found!")

        return values, self.geo

    def field(self, var, validtime=None):

        if validtime is None:
            validtime = []
            # raise Exception("You must set times to read forcing data")
        elif type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        else:
            validtime = [validtime]

        field, geo_in = self.read(var, validtime)
        # Reshape to fortran 2D style
        field = np.reshape(field, [geo_in.nlons, geo_in.nlats], order="F")
        return field, geo_in

    def points(self, var, geo_out, validtime=None, interpolation="nearest", cache=None):
        if validtime is not None and type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        field, geo_in = self.field(var, validtime=validtime)

        points, interpolator = SurfexFile.interpolate_field(self, field, geo_in, geo_out, interpolation=interpolation,
                                                            cache=cache)
        return points, interpolator


class TexteSurfexFile(SurfexFile):

    """
    Reading surfex TEXTE output
    """

    def __init__(self, geo, fname):
        SurfexFile.__init__(self,  fname, geo)
        self.file = None

    def read(self, variable, times):
        self.file = open(self.fname, mode="r")

        base_time = variable.basetime
        interval = variable.interval
        npatch = variable.patches

        if base_time is None:
            raise Exception("Basetime must be set for TEXTE")
        if interval is None:
            raise Exception("Interval must be set for TEXTE")

        if not isinstance(times, (list, tuple)):
            raise Exception("times must be list or tuple")

        values = np.array([])
        times_read = np.array([])
        end_of_line = self.geo.npoints * npatch
        this_time = np.empty(self.geo.npoints * npatch)

        t = 1
        col = 0
        for line in self.file.read().splitlines():

            words = line.split()
            if len(words) > 0:
                for i in range(0, len(words)):
                    val = float(words[i].replace("D", "E"))
                    if val == 1e+20:
                        val = np.nan
                    this_time[col] = val

                    col = col + 1
                    if col == end_of_line:

                        if times is None or (base_time + timedelta(seconds=(t * interval))) in times:
                            values = np.append(values, this_time)
                            times_read = np.append(times_read, base_time + timedelta(seconds=(t * interval)))
                            # print i, col, base_time + timedelta(seconds=(t * interval)), this_time

                        t = t + 1
                        col = 0
                        this_time[:] = np.nan
                        if i != len(words) - 1:
                            raise Exception("Dimension of domain does not match end of line! " +
                                            str(i) + " != " + str(len(words) - 1))

        if times_read.shape[0] > 0:
            values = np.reshape(values, [times_read.shape[0], this_time.shape[0]])
        else:
            print("No data found!")

        # print values.shape
        self.file.close()
        return values, self.geo

    def field(self, var, validtime=None):
        if validtime is None:
            raise Exception("You must set times to read forcing data")
        elif type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        else:
            validtime = [validtime]

        field, geo_in = self.read(var, validtime)
        # Reshape to fortran 2D style
        field = np.reshape(field, [geo_in.nlons, geo_in.nlats], order="F")
        return field, geo_in

    def points(self, var, geo_out, validtime=None, interpolation="nearest", cache=None):

        if validtime is not None and type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        field, geo_in = self.field(var, validtime=validtime)

        points, interpolator = SurfexFile.interpolate_field(self, field, geo_in, geo_out, interpolation=interpolation,
                                                            cache=cache)
        return points, interpolator


class ForcingFileNetCDF(SurfexFile):

    def __init__(self, fname, geo):
        self.fname = fname
        self.fh = Dataset(fname, "r")
        self.lons = self.fh.variables["LON"]
        self.lats = self.fh.variables["LAT"]
        self.nx = self.lons.shape[0]
        self.ny = self.lats.shape[0]
        SurfexFile.__init__(self, fname, geo)

    def read_field(self, variable, times):

        var = variable.varname
        field = None
        if self.fh.variables[var].shape[0] > 0:
            if len(self.fh.variables[var].dimensions) == 1:
                dimlen = self.fh.variables[var].shape[0]
                field = self.fh.variables[var][0:dimlen]
            else:
                if len(times) == 0:
                    raise Exception("You must set time!")

                times_read = []
                ndims = 0
                npoints = 0
                for dim in self.fh.variables[var].dimensions:
                    dimlen = self.fh.variables[var].shape[ndims]

                    if dim == "time":
                        times_for_var = self.fh.variables['time']
                        units = times_for_var.units
                        try:
                            t_cal = times_for_var.calendar
                        except AttributeError:  # Attribute doesn't exist
                            t_cal = u"gregorian"  # or standard

                        indices = []
                        [indices.append(i) for i in range(0, dimlen)]
                        times_for_var = num2date(times_for_var[indices], units=units, calendar=t_cal)
                        # print(times_for_var)
                        for times_to_read in range(0, len(times)):
                            # print(times_to_read, times[times_to_read])
                            for t in range(0, len(times_for_var)):
                                # print(t, times_for_var[t], times[times_to_read])
                                test_time = times_for_var[t].strftime("%Y%m%d%H")
                                test_time = datetime.strptime(test_time, "%Y%m%d%H")
                                if test_time == times[times_to_read]:
                                    times_read.append(t)
                                    print(t, times[times_to_read])
                    else:
                        npoints = dimlen

                    ndims = ndims + 1

                if npoints == 0:
                    raise Exception("No points found")

                if len(times_read) == 0 and len(times) > 0:
                    print(times)
                    raise Exception("Valid time not found in file!")

                field = self.fh.variables[var][times_read, 0: npoints]

        return field, self.geo

    def field(self, var, validtime=None):
        if validtime is None:
            validtime = []
            # raise Exception("You must set times to read forcing data")
        elif type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        else:
            validtime = [validtime]

        field, geo_in = self.read_field(var, validtime)
        # Reshape to fortran 2D style
        field = np.reshape(field, [geo_in.nlons, geo_in.nlats], order="F")
        return field, geo_in

    def points(self, var, geo_out, validtime=None, interpolation=None, cache=None):

        if validtime is not None and type(validtime) != datetime:
            raise Exception("validime must be a datetime object")
        field, geo_in = self.field(var, validtime=validtime)

        points, interpolator = SurfexFile.interpolate_field(self, field, geo_in, geo_out, interpolation=interpolation,
                                                            cache=cache)
        return points, interpolator


def read_surfex_field(varname, filename, validtime=None, basetime=None, patches=-1, layers=-1, fileformat=None,
                      filetype=None, geo=None, datatype=None, interval=None):

    if fileformat is None:
        fileformat, filetype = surfex.file.guess_file_format(filename, filetype)

    if filetype == "surf":
        if fileformat.lower() == "ascii":
            geo = surfex.file.AsciiSurfexFile(filename).geo
        elif fileformat.lower() == "nc":
            geo = surfex.file.NCSurfexFile(filename).geo
        else:
            if geo is None:
                raise NotImplementedError("Not implemnted and geo is None")
    elif geo is None:
        raise Exception("You need to provide a geo object. Filetype is: " + str(filetype))

    sfx_io = surfex.file.get_surfex_io_object(filename, filetype=filetype, fileformat=fileformat, geo=geo)
    var = surfex.file.SurfexFileVariable(varname, validtime=validtime, patches=patches, layers=layers,
                                         basetime=basetime, interval=interval, datatype=datatype)
    field, geo_out = sfx_io.field(var, validtime=validtime)
    return field


def read_surfex_points(varname, filename, geo_out, validtime=None, basetime=None, patches=-1, layers=-1,
                       fileformat=None, filetype=None, geo=None, datatype=None, interval=None, interpolation="nearest"):

    if fileformat is None:
        fileformat, filetype = surfex.file.guess_file_format(filename, filetype)

    if filetype == "surf":
        if fileformat.lower() == "ascii":
            geo = surfex.file.AsciiSurfexFile(filename).geo
        elif fileformat.lower() == "nc":
            geo = surfex.file.NCSurfexFile(filename).geo
        else:
            if geo is None:
                raise NotImplementedError("Not implemnted and geo is None")
    elif geo is None:
        raise Exception("You need to provide a geo object. Filetype is: " + str(filetype))

    sfx_io = surfex.file.get_surfex_io_object(filename, filetype=filetype, fileformat=fileformat, geo=geo)
    var = surfex.file.SurfexFileVariable(varname, validtime=validtime, patches=patches, layers=layers,
                                         basetime=basetime, interval=interval, datatype=datatype)
    field, geo_out = sfx_io.points(var, geo_out, validtime=validtime, interpolation=interpolation)
    return field


def parse_filepattern(file_pattern, basetime, validtime):

    # print(file_pattern)
    file_name = str(file_pattern)
    year = basetime.strftime('%Y')
    year2 = basetime.strftime('%y')
    month = basetime.strftime('%m')
    day = basetime.strftime('%d')
    hour = basetime.strftime('%H')
    dt = validtime-basetime
    l1 = "%d" % (dt.seconds / 3600)
    ll = "%02d" % (dt.seconds / 3600)
    lll = "%03d" % (dt.seconds / 3600)
    llll = "%04d" % (dt.seconds / 3600)
    file_name = file_name.replace('@YYYY@', year)
    file_name = file_name.replace('@YY@', year2)
    file_name = file_name.replace('@MM@', month)
    file_name = file_name.replace('@DD@', day)
    file_name = file_name.replace('@HH@', hour)
    file_name = file_name.replace('@L@', l1)
    file_name = file_name.replace('@LL@', ll)
    file_name = file_name.replace('@LLL@', lll)
    file_name = file_name.replace('@LLLL@', llll)
    return file_name