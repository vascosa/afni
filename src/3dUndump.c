/*****************************************************************************
   Major portions of this software are copyrighted by the Medical College
   of Wisconsin, 1994-2000, and are released under the Gnu General Public
   License, Version 2.  See the file README.Copyright for details.
******************************************************************************/
   
#include "mrilib.h"

/*-- these macros stolen from file thd.h --*/

#define ORCODE(aa) \
  ( (aa)=='R' ? ORI_R2L_TYPE : (aa)=='L' ? ORI_L2R_TYPE : \
    (aa)=='P' ? ORI_P2A_TYPE : (aa)=='A' ? ORI_A2P_TYPE : \
    (aa)=='I' ? ORI_I2S_TYPE : (aa)=='S' ? ORI_S2I_TYPE : ILLEGAL_TYPE )

#define OR3OK(x,y,z) ( ((x)&6) + ((y)&6) + ((z)&6) == 6 )

/*------------------------------------------------------------------------*/

void Syntax(char * msg)
{
   if( msg != NULL ){
      fprintf(stderr,"*** %s\n",msg) ; exit(1) ;
   }

   printf(
    "Usage: 3dUndump [options] infile ...\n"
    "Assembles a 3D dataset from an ASCII list of coordinates and\n"
    "(optionally) values.\n"
    "\n"
    "Options:\n"
    "  -prefix ppp  = 'ppp' is the prefix for the output dataset\n"
    "                   [default = undump].\n"
    "  -master mmm  = 'mmm' is the master dataset, whose geometry\n"
    "    *OR*           will determine the geometry of the output.\n"
    "  -dimen I J K = Sets the dimensions of the output dataset to\n"
    "                   be I by J by K voxels.  (Each I, J, and K\n"
    "                   must be >= 2.)  This option can be used to\n"
    "                   create a dataset of a specific size for test\n"
    "                   purposes, when no suitable master exists.\n"
    "          ** N.B.: Exactly one of -master or -dimen must be given.\n"
    "  -datum type  = 'type' determines the voxel data type of the\n"
    "                   output, which may be byte, short, or float\n"
    "                   [default = short].\n"
    "  -dval vvv    = 'vvv' is the default value stored in each\n"
    "                   input voxel that does not have a value\n"
    "                   supplied in the input file [default = 1].\n"
    "  -fval fff    = 'fff' is the fill value, used for each voxel\n"
    "                   in the output dataset that is NOT listed\n"
    "                   in the input file [default = 0].\n"
    "  -ijk         = Coordinates in the input file are (i,j,k) index\n"
    "       *OR*        triples, as might be output by 3dmaskdump.\n"
    "  -xyz         = Coordinates in the input file are (x,y,z)\n"
    "                   spatial coordinates, in mm.  If neither\n"
    "                   -ijk or -xyz is given, the default is -ijk.\n"
    "          ** N.B.: -xyz can only be used with -master. If -dimen\n"
    "                   is used to specify the size of the output dataset,\n"
    "                   (x,y,z) coordinates are not defined (until you\n"
    "                   use 3drefit to define the spatial structure).\n"
    "  -orient code = Specifies the coordinate order used by -xyz.\n"
    "                   The code must be 3 letters, one each from the pairs\n"
    "                   {R,L} {A,P} {I,S}.  The first letter gives the\n"
    "                   orientation of the x-axis, the second the orientation\n"
    "                   of the y-axis, the third the z-axis:\n"
    "                     R = right-to-left         L = left-to-right\n"
    "                     A = anterior-to-posterior P = posterior-to-anterior\n"
    "                     I = inferior-to-superior  S = superior-to-inferior\n"
    "                   If -orient isn't used, then the coordinate order of the\n"
    "                   -master dataset is used to interpret (x,y,z) inputs.\n"
    "          ** N.B.: If -dimen is used (which implies -ijk), then the\n"
    "                   only use of -orient is to specify the axes ordering\n"
    "                   of the output dataset.  If -master is used instead,\n"
    "                   the output dataset's axes ordering is the same as the\n"
    "                   -master dataset's, regardless of -orient.\n"
    "\n"
    "Input File Format:\n"
    " The input file(s) are ASCII files, with one voxel specification per\n"
    " line.  A voxel specification is 3 numbers (-ijk or -xyz coordinates),\n"
    " with an optional 4th number giving the voxel value.  For example:\n"
    "\n"
    "   1 2 3 \n"
    "   3 2 1 5\n"
    "   5.3 6.2 3.7\n"
    "   // this line illustrates a comment\n"
    "\n"
    " The first line puts a voxel (with value given by -dval) at point\n"
    " (1,2,3).  The second line puts a voxel (with value 5) at point (3,2,1).\n"
    " The third line puts a voxel (with value given by -dval) at point\n"
    " (5.3,6.2,3.7).  If -ijk is in effect, and fractional coordinates\n"
    " are given, they will be rounded to the nearest integers; for example,\n"
    " the third line would be equivalent to (i,j,k) = (5,6,4).\n"
    "\n"
    "Notes:\n"
    "* This program creates a 1 sub-brick file.  You can 'glue' multiple\n"
    "   files together using 3dbucket or 3dTcat to make multi-brick datasets.\n"
    "* If an input filename is '-', then stdin is used.\n"
    "* By default, the output dataset is of type '-fim', unless the -master\n"
    "   dataset is an anat type.  You can change the output type using\n"
    "   3drefit.\n"
    "* You could use program 1dcat to extract specific columns from a\n"
    "   multi-column rectangular file (e.g., to get a specific sub-brick\n"
    "   from the output of 3dmaskdump).\n"
    "\n"
    "-- RWCox -- October 2000\n"
   ) ;

   exit(0) ;
}

/*---------------------------------------------------------------------------*/

#define NBUF 1024  /* line buffer size */

int main( int argc , char * argv[] )
{
   int do_ijk=1 , dimen_ii=0 , dimen_jj=0 , dimen_kk=0 , datum=MRI_short ;
   THD_3dim_dataset *mset=NULL ;
   char * prefix="undump" , * orcode=NULL ;
   THD_coorder cord ;
   float dval_float=1.0 , fval_float=0.0 , * fbr=NULL ;
   short dval_short=1   , fval_short=0   , * sbr=NULL ;
   byte  dval_byte =1   , fval_byte =0   , * bbr=NULL ;

   FILE * fp ;
   THD_3dim_dataset * dset ;
   int iarg , ii,jj,kk,ll,ijk , nx,ny,nz , nxyz , nn ;
   float      xx,yy,zz,vv ;
   char linbuf[NBUF] , * cp ;

   float xxdown,xxup , yydown,yyup , zzdown,zzup ;

   /*-- help? --*/

   if( argc < 3 || strcmp(argv[1],"-help") == 0 ) Syntax(NULL) ;

   /*-- 20 Apr 2001: addto the arglist, if user wants to [RWCox] --*/

   machdep() ; 
   { int new_argc ; char ** new_argv ;
     addto_args( argc , argv , &new_argc , &new_argv ) ;
     if( new_argv != NULL ){ argc = new_argc ; argv = new_argv ; }
   }

   /*-- command line options --*/

   iarg = 1 ;
   while( iarg < argc && argv[iarg][0] == '-' ){

      if( strcmp(argv[iarg],"-") == 0 ){    /* a single - is an input filename */
         break ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-prefix") == 0 ){
         if( iarg+1 >= argc )
            Syntax("-prefix: no argument follows!?") ;
         else if( !THD_filename_ok(argv[++iarg]) )
            Syntax("-prefix: Illegal prefix given!") ;
         prefix = argv[iarg] ;
         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-master") == 0 ){
         if( iarg+1 >= argc )
            Syntax("-master: no argument follows!?") ;
         else if( mset != NULL )
            Syntax("-master: can't have two -master options!") ;
         else if( dimen_ii > 0 )
            Syntax("-master: conflicts with previous -dimen!") ;

         mset = THD_open_dataset( argv[++iarg] ) ;
         if( mset == NULL )
            Syntax("-master: can't open dataset" ) ;

         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-dimen") == 0 ){
         if( iarg+3 >= argc )
            Syntax("-dimen: don't have 3 arguments following!?") ;
         else if( mset != NULL )
            Syntax("-dimen: conflicts with previous -master!") ;
         else if( dimen_ii > 0 )
            Syntax("-dimen: can't have two -dimen options!") ;
         dimen_ii = strtol(argv[++iarg],NULL,10) ;
         dimen_jj = strtol(argv[++iarg],NULL,10) ;
         dimen_kk = strtol(argv[++iarg],NULL,10) ;
         if( dimen_ii < 2 || dimen_jj < 2 || dimen_kk < 2 )
            Syntax("-dimen: values following are not all >= 2!") ;

         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-datum") == 0 ){
         if( ++iarg >= argc )
            Syntax("-datum: no argument follows?!") ;

         if( strcmp(argv[iarg],"short") == 0 )
            datum = MRI_short ;
         else if( strcmp(argv[iarg],"float") == 0 )
            datum = MRI_float ;
         else if( strcmp(argv[iarg],"byte") == 0 )
            datum = MRI_byte ;
         else
            Syntax("-datum: illegal type given!") ;

         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-dval") == 0 ){
         if( iarg+1 >= argc )
            Syntax("-dval: no argument follows!?") ;

         dval_float = strtod( argv[++iarg] , NULL ) ;
         dval_short = (short) rint(dval_float) ;
         dval_byte  = (byte)  dval_short ;
         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-fval") == 0 ){
         if( iarg+1 >= argc )
            Syntax("-fval: no argument follows!?") ;

         fval_float = strtod( argv[++iarg] , NULL ) ;
         fval_short = (short) rint(fval_float) ;
         fval_byte  = (byte)  fval_short ;
         iarg++ ; continue ;
      }

      if( strcmp(argv[iarg],"-ijk") == 0 ){
         do_ijk = 1 ;
         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-xyz") == 0 ){
         do_ijk = 0 ;
         iarg++ ; continue ;
      }

      /*-----*/

      if( strcmp(argv[iarg],"-orient") == 0 ){
         int xx,yy,zz ;
         if( iarg+1 >= argc )
            Syntax("-orient: no argument follows!?") ;

         orcode = argv[++iarg] ;
         if( strlen(orcode) != 3 )
            Syntax("-orient: illegal argument follows") ;

         xx = ORCODE(orcode[0]) ; yy = ORCODE(orcode[1]) ; zz = ORCODE(orcode[2]) ;
         if( xx < 0 || yy < 0 || zz < 0 || !OR3OK(xx,yy,zz) )
            Syntax("-orient: illegal argument follows") ;

         iarg++ ; continue ;
      }

      /*-----*/

      fprintf(stderr,"*** Unknown option: %s\n",argv[iarg]) ; exit(1) ;

   } /* end of loop over command line options */

   /*-- check for inconsistencies --*/

   if( iarg >= argc )
      Syntax("No input files on command line!?") ;

   if( do_ijk == 0 && mset == NULL )
      Syntax("Can't use -xyz without -master also!") ;

   if( mset == NULL && dimen_ii < 2 )
      Syntax("Must use exactly one of -master or -dimen options on command line");

   if( (datum == MRI_short && dval_short == fval_short) ||
       (datum == MRI_float && dval_float == fval_float) ||
       (datum == MRI_byte  && dval_byte  == fval_byte )   ){

      fprintf(stderr,"+++ Warning: -dval and -fval are the same!\n") ;
   }

   /*-- set orcode to value from -master, if this is needed --*/

   if( mset != NULL && do_ijk == 0 && orcode == NULL ){
      orcode = malloc(4) ;
      orcode[0] = ORIENT_typestr[mset->daxes->xxorient][0] ;
      orcode[1] = ORIENT_typestr[mset->daxes->yyorient][0] ;
      orcode[2] = ORIENT_typestr[mset->daxes->zzorient][0] ;
      orcode[3] = '\0' ;
   }

   THD_coorder_fill( orcode , &cord ) ;  /* setup coordinate order */

   /*-- make empty dataset --*/

   if( mset != NULL ){                 /* from -master */

      dset = EDIT_empty_copy( mset ) ;
      EDIT_dset_items( dset ,
                          ADN_prefix    , prefix ,
                          ADN_datum_all , datum ,
                          ADN_nvals     , 1 ,
                          ADN_ntt       , 0 ,
                          ADN_func_type , ISANAT(mset) ? mset->func_type
                                                       : FUNC_FIM_TYPE ,
                       ADN_none ) ;

   } else {                            /* from nothing */

     THD_ivec3 iv_nxyz   , iv_xyzorient ;
     THD_fvec3 fv_xyzorg , fv_xyzdel ;

     LOAD_IVEC3( iv_nxyz , dimen_ii , dimen_jj , dimen_kk ) ;
     LOAD_IVEC3( iv_xyzorient , cord.xxor , cord.yyor , cord.zzor ) ;
     LOAD_FVEC3( fv_xyzdel ,
                 ORIENT_sign[iv_xyzorient.ijk[0]]=='+' ? 1.0 : -1.0 ,
                 ORIENT_sign[iv_xyzorient.ijk[1]]=='+' ? 1.0 : -1.0 ,
                 ORIENT_sign[iv_xyzorient.ijk[2]]=='+' ? 1.0 : -1.0  ) ;
     LOAD_FVEC3( fv_xyzorg ,
                 ORIENT_sign[iv_xyzorient.ijk[0]]=='+' ? -0.5*dimen_ii : 0.5*dimen_ii,
                 ORIENT_sign[iv_xyzorient.ijk[1]]=='+' ? -0.5*dimen_jj : 0.5*dimen_jj,
                 ORIENT_sign[iv_xyzorient.ijk[2]]=='+' ? -0.5*dimen_kk : 0.5*dimen_kk ) ;

     dset = EDIT_empty_copy( NULL ) ;

     EDIT_dset_items( dset ,
                       ADN_nxyz      , iv_nxyz ,
                       ADN_xyzdel    , fv_xyzdel ,
                       ADN_xyzorg    , fv_xyzorg ,
                       ADN_xyzorient , iv_xyzorient ,
                       ADN_prefix    , prefix ,
                       ADN_datum_all , datum ,
                       ADN_nvals     , 1 ,
                       ADN_ntt       , 0 ,
                       ADN_type      , HEAD_FUNC_TYPE ,
                       ADN_func_type , FUNC_FIM_TYPE ,
                    ADN_none ) ;
   }

   if( THD_is_file(DSET_HEADNAME(dset)) )
      Syntax("Output dataset already exists -- can't overwrite") ;

   /*-- make empty brick array for dataset --*/

   EDIT_substitute_brick( dset , 0 , datum , NULL ) ;  /* will make array */

   nx = DSET_NX(dset); ny = DSET_NY(dset); nz = DSET_NZ(dset); nxyz = nx*ny*nz;

   /*-- fill with the -fval value --*/

   switch( datum ){
      case MRI_short:
         sbr = (short *) DSET_BRICK_ARRAY(dset,0) ;
         for( ii=0 ; ii < nxyz ; ii++ ) sbr[ii] = fval_short ;
      break ;

      case MRI_float:
         fbr = (float *) DSET_BRICK_ARRAY(dset,0) ;
         for( ii=0 ; ii < nxyz ; ii++ ) fbr[ii] = fval_float ;
      break ;

      case MRI_byte:
         bbr = (byte *) DSET_BRICK_ARRAY(dset,0) ;
         for( ii=0 ; ii < nxyz ; ii++ ) bbr[ii] = fval_byte ;
      break ;
   }

   /* 24 Nov 2000: get the bounding box for the dataset */

   if( !do_ijk ){
#ifndef EXTEND_BBOX
      xxdown = dset->daxes->xxmin - 0.501 * fabs(dset->daxes->xxdel) ;
      xxup   = dset->daxes->xxmax + 0.501 * fabs(dset->daxes->xxdel) ;
      yydown = dset->daxes->yymin - 0.501 * fabs(dset->daxes->yydel) ;
      yyup   = dset->daxes->yymax + 0.501 * fabs(dset->daxes->yydel) ;
      zzdown = dset->daxes->zzmin - 0.501 * fabs(dset->daxes->zzdel) ;
      zzup   = dset->daxes->zzmax + 0.501 * fabs(dset->daxes->zzdel) ;
#else
      xxdown = dset->daxes->xxmin ;
      xxup   = dset->daxes->xxmax ;
      yydown = dset->daxes->yymin ;
      yyup   = dset->daxes->yymax ;
      zzdown = dset->daxes->zzmin ;
      zzup   = dset->daxes->zzmax ;
#endif
   }

   /*-- loop over input files and read them line by line --*/

   for( ; iarg < argc ; iarg++ ){  /* iarg is already set at start of this loop */

      /* get input file ready to read */

      if( strcmp(argv[iarg],"-") == 0 ){  /* stdin */
         fp = stdin ;
      } else {                            /* OK, open the damn file */
         fp = fopen( argv[iarg] , "r" ) ;
         if( fp == NULL ){
            fprintf(stderr,
                    "+++ Warning: can't open input file %s -- skipping it\n",
                    argv[iarg]) ;
            continue ;                    /* skip to end of iarg loop */
         }
      }

      /* read lines, process and store */

      ll = 0 ;
      while(1){
         ll++ ;                               /* line count */
         cp = fgets( linbuf , NBUF , fp ) ;
         if( cp == NULL ) break ;             /* end of file => end of loop */
         kk = strlen(linbuf) ;
         if( kk == 0 ) continue ;             /* empty line => get next line */

         /* find 1st nonblank */

         for( ii=0 ; ii < kk && isspace(linbuf[ii]) ; ii++ ) ; /* nada */
         if( ii == kk ) continue ;                                 /* all blanks */
         if( linbuf[ii] == '/' && linbuf[ii+1] == '/' ) continue ; /* comment */

         /* scan line for data */

         vv = dval_float ;
         nn = sscanf(linbuf+ii , "%f%f%f%f" , &xx,&yy,&zz,&vv ) ;
         if( nn < 3 ){
            fprintf(stderr,"+++ Warning: file %s line %d: incomplete\n",argv[iarg],ll) ;
            continue ;
         }

         /* get voxel index into (ii,jj,kk) */

         if( do_ijk ){   /* inputs are (ii,jj,kk) themselves */

            ii = (int) rint(xx) ; jj = (int) rint(yy) ; kk = (int) rint(zz) ;
            if( ii < 0 || ii >= nx ){
               fprintf(stderr,
                       "+++ Warning: file %s line %d: i index=%d is invalid\n",
                       argv[iarg],ll,ii) ;
               continue ;
            }
            if( jj < 0 || jj >= ny ){
               fprintf(stderr,
                       "+++ Warning: file %s line %d: j index=%d is invalid\n",
                       argv[iarg],ll,jj) ;
               continue ;
            }
            if( kk < 0 || kk >= nz ){
               fprintf(stderr,
                       "+++ Warning: file %s line %d: k index=%d is invalid\n",
                       argv[iarg],ll,kk) ;
               continue ;
            }

         } else {  /* inputs are coordinates => must convert to index */

            THD_fvec3 mv , dv ;                              /* temp vectors */
            THD_ivec3 iv ;

            THD_coorder_to_dicom( &cord , &xx,&yy,&zz ) ;    /* to Dicom order */
            LOAD_FVEC3( dv , xx,yy,zz ) ;
            mv = THD_dicomm_to_3dmm( dset , dv ) ;           /* to Dataset order */

            /* 24 Nov 2000: check (xx,yy,zz) for being inside the box */

            if( mv.xyz[0] < xxdown || mv.xyz[0] > xxup ){
               fprintf(stderr,"+++ Warning: file %s line %d: x coord=%g is invalid\n" ,
                       argv[iarg],ll,xx ) ;
               continue ;
            }
            if( mv.xyz[1] < yydown || mv.xyz[1] > yyup ){
               fprintf(stderr,"+++ Warning: file %s line %d: y coord=%g is invalid\n" ,
                       argv[iarg],ll,yy ) ;
               continue ;
            }
            if( mv.xyz[0] < zzdown || mv.xyz[0] > zzup ){
               fprintf(stderr,"+++ Warning: file %s line %d: z coord=%g is invalid\n" ,
                       argv[iarg],ll,zz ) ;
               continue ;
            }

            iv = THD_3dmm_to_3dind( dset , mv ) ;            /* to Dataset index */
            ii = iv.ijk[0]; jj = iv.ijk[1]; kk = iv.ijk[2];  /* save */
         }

         /* now load voxel */

         ijk = ii + jj*nx + kk*nx*ny ;
         switch( datum ){
            case MRI_float: fbr[ijk] = vv               ; break ;
            case MRI_short: sbr[ijk] = (short) rint(vv) ; break ;
            case MRI_byte:  bbr[ijk] = (byte)  rint(vv) ; break ;
         }

      } /* end of loop over input lines */

      /* close input file */

      if( fp != stdin ) fclose( fp ) ;

   } /* end of loop over input files */

   fprintf(stderr,"+++ Writing results to dataset %s\n",DSET_FILECODE(dset)) ;
   DSET_write(dset) ;
   exit(0) ;
}
