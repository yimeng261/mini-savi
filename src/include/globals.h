/*
 *****************************************************
 *
 *  SaVi by Lloyd Wood (lloydwood@users.sourceforge.net),
 *          Patrick Worfolk (worfolk@alum.mit.edu) and
 *          Robert Thurman.
 *
 *  Copyright (c) 1997 by The Geometry Center.
 *  Also Copyright (c) 2017 by Lloyd Wood.
 *
 *  This file is part of SaVi.  SaVi is free software;
 *  you can redistribute it and/or modify it only under
 *  the terms given in the file COPYRIGHT which you should
 *  have received along with this file.  SaVi may be
 *  obtained from:
 *  http://savi.sourceforge.net/
 *  http://www.geom.uiuc.edu/locate/SaVi
 *
 *****************************************************
 *
 * globals.h
 *
 * Global variable declarations
 *
 * $Id: globals.h,v 1.58 2017/06/07 21:34:22 lloydwood Exp $
 */

#ifndef _GLOBALS_H_
#define _GLOBALS_H_

#define LENGTH_STRING_BUFFER 256

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

extern char cmd[LENGTH_STRING_BUFFER];

extern char command_switches[LENGTH_STRING_BUFFER];

extern int geomview_module; /* TRUE if program is a geomview module */
extern int fake_geomview_module; /* TRUE if pretending to run under geomview */
extern int geomview_logo; /* TRUE if SaVi logo is shown on camera */

extern int texture_flag; /* TRUE if we're texturemapping */
extern int geomview_detailed_texturemap; /* TRUE if file available */
extern int geomview_dynamic_texture_flag; /* TRUE if sending coverage to Geomview. */
extern int geomview_texture_with_map; /* TRUE if bitmap earthmap included */
extern int geomview_stream_textures; /* TRUE if we don't need a scratchfile */
extern int geomview_compress2_textures; /* TRUE if Geomview doesn't have to spawn gzip */

extern int geomview_compressed_images; /* FALSE if no zlib or -uncompressed. */

extern int geomview_sun_lighting; /* TRUE if we trust geomview's light sources */

extern int footprints_flag; /* TRUE if we want to see edges, inc sun terminator */
extern int plane_flag; /* TRUE if we want to see equatorial plane */
extern int sun_flag; /* TRUE if we want to see sun lighting */
extern int fisheye_viewpoint_flag; /* TRUE if we want to plot location on coverage */

extern int debug;
extern int splash_about;
extern int buttons_menu;

typedef enum {
  MASK_ELEVATION=0, SATELLITE_CONE
} coverage_types;

typedef enum {
  J0=0, J2
} orbit_models;

extern int orbit_model;

/* We don't yet have a proper map for SINUSOIDAL centred on 0 deg lat. */
typedef enum {
  UNPROJECTED_MASK=0,
  UNPROJECTED,
  CYLINDRICAL,
  SINUSOIDAL,
  SINUSOIDAL_90,
  SPHERICAL,
  SPHERICAL_90,
  NUM_PROJECTIONS
} coverage_projections;

extern int coverage_projection;

/*
 * sinusoidal and cylindrical projections can be centered on America
 * and rotated -90 degrees
 * cylindrical and unprojected projections are normal - 0 degrees rotation.
 * Just stretch the coverage window sideways to see tiling.
 */
extern int Longitude_Center_Line;
extern int coverage_display_center_longitude;

extern int min_transmit_altitude;
extern int max_transmit_altitude;

/* number of colors in use by coverage panel map display */
extern int NUM_COLORS;

extern char *first_filename;

extern char EMPTY_str[];  /* empty string */
extern char *Version; /* string containing who and when compiled */

extern unsigned int motion; /* TRUE to move satellites, FALSE to stop them */
extern unsigned int reset; /* TRUE to reset satellites to original positions */
extern unsigned int single_step; /* TRUE if take only one step */

extern double equatorial_exclusion_angle; /* half-width/highest latitude of geo frequency exclusion belt */
extern double parallels_angle; /* angle marked out in fisheye for parallel lines of latitude */

extern double delta_t; /* time increment */
extern double coverage_angle; /* angle for footprints */
extern int coverage_type; /* mask elevation or the less-used cone angle */
extern double tracks_interval; /* time interval for computing ground tracks */
extern unsigned int transforms_needed; /* flag for sending transforms to gv */

/* size of image for coverage display */
extern int Image_Width;
extern int Image_Height;

/* size of fisheye */
extern int Fisheye_Diameter;

/* coverage colors */
extern int DIV0, DIV1, DIV2, DIV3, DIV4, DIV5, DIV6, DIV7, DIV8, DIV9;
extern int DIV10, DIV11, DIV12, DIV13, DIV14, DIV15, DIV16, DIV17, DIV18, DIV19;

extern int DEC0, DEC1, DEC2, DEC3, DEC4, DEC5, DEC6, DEC7, DEC8, DEC9;
extern int DEC10, DEC11, DEC12, DEC13, DEC14, DEC15, DEC16, DEC17, DEC18, DEC19;

#endif
/* !_GLOBALS_H_ */
