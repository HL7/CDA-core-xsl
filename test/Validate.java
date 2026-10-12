import javax.xml.validation.*;
import javax.xml.transform.stream.StreamSource;
import java.io.File;

/** Validates an XML file against an XSD schema. Usage: java Validate schema.xsd file.xml */
public class Validate {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java Validate schema.xsd file.xml");
            System.exit(2);
        }
        SchemaFactory sf = SchemaFactory.newInstance("http://www.w3.org/2001/XMLSchema");
        Schema schema = sf.newSchema(new File(args[0]));
        Validator validator = schema.newValidator();
        validator.validate(new StreamSource(new File(args[1])));
        System.out.println("PASS: " + args[1] + " validates against " + args[0]);
    }
}
